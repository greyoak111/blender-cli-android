#!/usr/bin/env python3
"""给 cccodroid 的 blender 组件装「Debian arm64 用户空间」（Blender 及其依赖闭包）。

为什么是 Debian：Blender 官方没有 Linux arm64 构建（只给 x64 / macOS-arm64 / Windows-arm64），
Debian 的 arm64 包是能拿到的最新版。glibc 运行时用 Termux 的（安卓上唯一能跑的那份），
所以这里只装 Debian 的其余包 —— libc6 跳过。

安全：
  · 索引链：先取 dists/<套件>/InRelease，Packages.gz 必须和它里面记的 SHA256 对上；
    每个 .deb 再拿 Packages 里的 SHA256 核对。对不上就停。不关证书校验。
    （InRelease 的 GPG 签名没验：工具包里没有 gpgv，也没有 Debian 钥匙环。信任根是到
    deb.debian.org 的 HTTPS；InRelease 这一步把信任收拢到一个文件上。）
  · 解包只许落在目标目录里：成员名带 ..、软链 / 硬链指到目录外、经已有软链绕出去的，一律跳过。
  · 不在系统分区写任何东西。

用法: install-debroot.py <目标目录> [--dry-run] [--jobs N]
  --dry-run   只算闭包和体积，不下载
  --jobs N    并发线程数（默认 4）
环境变量:
  CCODROID_BLENDER_SUITE   Debian 套件（默认 trixie）
  CCODROID_BLENDER_MIRROR  镜像（默认 https://deb.debian.org/debian/）
"""
import gzip
import hashlib
import io
import json
import lzma
import os
import re
import sys
import tarfile
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SUITE = os.environ.get("CCODROID_BLENDER_SUITE", "trixie")
MIRRORS = [os.environ.get("CCODROID_BLENDER_MIRROR", "https://deb.debian.org/debian/"),
           "https://ftp.debian.org/debian/"]
ARCH = "arm64"
COMPS = ["main", "contrib", "non-free"]
ROOTS = ["blender", "python3-numpy", "libegl1"]
# 组件描述、skill 写的是这个上游版本。Debian 点版本把 blender 升了也照装（安全更新不该被挡），
# 但要明说 —— 实际版本以 blender --selftest 的总结行为准。
EXPECT_BLENDER = "4.3.2"
# 用 Termux 的 glibc：安卓上唯一能用的 glibc 运行时（组件依赖的 glibc 包已提供）
SKIP = {"libc6"}

LOCK = threading.Lock()


def http_get(url, timeout=180):
    # 不关证书校验：索引（Packages.gz）与 .deb 都从这条连接取，
    # 不校验的话下面「核对 SHA256」就形同虚设。
    req = urllib.request.Request(url, headers={"User-Agent": "cccodroid-blender/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_deb822(block):
    fields, last = {}, None
    for line in block.split("\n"):
        m = re.match(r"^([A-Za-z0-9-]+):\s?(.*)$", line)
        if m:
            last = m[1]
            fields[last] = m[2]
        elif last and line.startswith(" "):
            fields[last] += "\n" + line.strip()
    return fields


def ver_key(v):
    return [int(x) if x.isdigit() else x for x in re.split(r"[.\-~+]", v)]


def release_sums(mirror):
    """InRelease 里 SHA256 一节：{相对路径: (sha256, 大小)}"""
    text = http_get(f"{mirror}dists/{SUITE}/InRelease").decode("utf-8", "replace")
    sums, on = {}, False
    for line in text.split("\n"):
        if line.startswith("SHA256:"):
            on = True
            continue
        if on:
            if not line.startswith(" "):
                break
            parts = line.split()
            if len(parts) == 3:
                sums[parts[2]] = (parts[0].lower(), int(parts[1]))
    if not sums:
        raise ValueError("InRelease 里没有 SHA256 一节")
    return sums


def load_index():
    for mirror in MIRRORS:
        idx = {}
        try:
            sums = release_sums(mirror)
            for comp in COMPS:
                rel = f"{comp}/binary-{ARCH}/Packages.gz"
                gz = http_get(f"{mirror}dists/{SUITE}/{rel}")
                want = sums.get(rel)
                got = hashlib.sha256(gz).hexdigest()
                if not want or want[0] != got:
                    raise ValueError(f"{rel} 和 InRelease 对不上（InRelease {want[0][:16] if want else '无此条'}… / 实得 {got[:16]}…）")
                raw = gzip.decompress(gz)
                for block in raw.decode("utf-8", "replace").split("\n\n"):
                    f = parse_deb822(block)
                    name = f.get("Package")
                    if not name:
                        continue
                    cur = idx.get(name)
                    if cur is None or ver_key(f.get("Version", "")) > ver_key(cur["version"]):
                        idx[name] = {
                            "version": f.get("Version", "?"),
                            "filename": f.get("Filename", ""),
                            "size": int(f.get("Size", 0) or 0),
                            "installed": int(f.get("Installed-Size", 0) or 0),
                            "sha256": (f.get("SHA256", "") or "").lower(),
                            "deps": f.get("Depends", "") or "",
                            "pre": f.get("Pre-Depends", "") or "",
                        }
            print(f"  索引：Debian {SUITE}/{ARCH} · {len(idx)} 个包 · {mirror}")
            return mirror, idx
        except Exception as e:                                     # noqa: BLE001
            print(f"  镜像不可用 {mirror}: {e}")
    raise SystemExit("所有镜像都拿不到索引")


def parse_deps(s):
    out = []
    for grp in s.split(","):
        parts = grp.split("|")[0].strip().split()
        name = re.sub(r":.*$", "", re.sub(r"\(.*?\)", "", parts[0] if parts else "")).strip()
        if name and not name.startswith("${"):
            out.append(name)
    return out


def closure(idx, roots):
    seen, missing, order = set(), [], []
    queue = list(roots)
    dl = inst = 0
    while queue:
        n = queue.pop(0)
        if n in seen or n in SKIP:
            continue
        p = idx.get(n)
        if not p:
            missing.append(n)
            continue
        seen.add(n)
        order.append(n)
        dl += p["size"]
        inst += p["installed"]
        queue.extend(parse_deps(p["deps"]))
        queue.extend(parse_deps(p["pre"]))
    return order, missing, dl, inst


# ── .deb 解包 ────────────────────────────────────────────────────────
def ar_members(buf):
    if buf[:8] != b"!<arch>\n":
        raise ValueError("不是 ar 归档")
    off = 8
    while off + 60 <= len(buf):
        hdr = buf[off:off + 60]
        name = hdr[:16].decode("utf-8", "replace").strip().rstrip("/")
        try:
            size = int(hdr[48:58].decode().strip())
        except ValueError:
            break
        yield name, buf[off + 60:off + 60 + size]
        off += 60 + size + (size % 2)


def tar_stream(name, blob):
    if name.endswith(".xz"):
        return lzma.LZMAFile(io.BytesIO(blob))
    if name.endswith(".gz"):
        return gzip.GzipFile(fileobj=io.BytesIO(blob))
    if name.endswith(".zst"):
        try:
            from compression import zstd                       # Python 3.14+
            return io.BytesIO(zstd.decompress(blob))
        except ImportError:
            import zstandard
            return io.BytesIO(zstandard.ZstdDecompressor().decompress(blob))
    return io.BytesIO(blob)


def inside(root_real, path):
    """path（解析软链后）是否落在 root_real 里"""
    rp = os.path.realpath(path)
    return rp == root_real or rp.startswith(root_real + os.sep)


def extract_deb(deb, root, stats):
    root_real = os.path.realpath(root)
    for name, blob in ar_members(deb):
        if not name.startswith("data.tar"):
            continue
        tf = tarfile.open(fileobj=tar_stream(name, blob), mode="r|")
        for m in tf:
            rel = m.name.lstrip("./").lstrip("/")
            if not rel:
                continue
            dst = os.path.join(root, rel)
            # 成员名带 ..、或父目录经已有软链绕到根外：跳过（Debian 官方包不会这样，防的是坏包）
            if ".." in rel.split("/") or not inside(root_real, os.path.dirname(dst) or root):
                with LOCK:
                    stats["skipped"] += 1
                continue
            try:
                if m.isdir():
                    os.makedirs(dst, exist_ok=True)
                    continue
                parent = os.path.dirname(dst)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                if m.issym():
                    target = m.linkname
                    if target.startswith("/"):
                        # Debian 包里有用绝对路径指到 /lib、/usr/lib 的软链；
                        # 我们的根不是 "/"，改写成根内路径
                        target = os.path.join(root, target.lstrip("/"))
                    # 相对软链解析后也得在根内（只按字面算，目标此刻可能还没解出来）
                    resolved = os.path.normpath(os.path.join(os.path.dirname(dst), target))
                    if not (resolved == root_real or resolved.startswith(root_real + os.sep)
                            or resolved == root or resolved.startswith(root + os.sep)):
                        raise OSError("软链指到根外：" + m.linkname)
                    if os.path.lexists(dst):
                        os.remove(dst)
                    os.symlink(target, dst)
                    key = "links"
                elif m.islnk():
                    src = os.path.join(root, m.linkname.lstrip("./").lstrip("/"))
                    if ".." in m.linkname.split("/") or not inside(root_real, src):
                        raise OSError("硬链指到根外：" + m.linkname)
                    if not os.path.exists(src):
                        key = "skipped"
                    else:
                        if os.path.lexists(dst):
                            os.remove(dst)
                        os.link(src, dst)
                        key = "links"
                elif m.isfile():
                    if os.path.lexists(dst):
                        os.remove(dst)
                    src_f = tf.extractfile(m)
                    with open(dst, "wb") as out:
                        while True:
                            b = src_f.read(1 << 20)
                            if not b:
                                break
                            out.write(b)
                    os.chmod(dst, m.mode & 0o7777)
                    key = "files"
                else:
                    key = "skipped"
            except (OSError, tarfile.TarError):
                key = "skipped"
            with LOCK:
                stats[key] += 1
        tf.close()
        return
    raise ValueError("没有 data.tar.*")


def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    jobs = 4
    if "--jobs" in argv:
        i = argv.index("--jobs")
        jobs = max(1, int(argv[i + 1]))
        del argv[i:i + 2]
    argv = [a for a in argv if not a.startswith("--")]
    if len(argv) != 1:
        print("用法: install-debroot.py <目标目录> [--dry-run] [--jobs N]", file=sys.stderr)
        return 2
    root = os.path.abspath(argv[0])
    base = os.path.dirname(root)
    cache = os.path.join(base, "debcache")
    marker = os.path.join(base, "installed.json")

    print(f"Debian 用户空间（Blender 4.3.2 · {SUITE}/{ARCH}）")
    print(f"  根包：{' '.join(ROOTS)}    跳过：{', '.join(sorted(SKIP))}（用 Termux 的 glibc）")
    mirror, idx = load_index()
    order, missing, dl, inst = closure(idx, ROOTS)
    bv = idx.get("blender", {}).get("version", "?")
    if not bv.startswith(EXPECT_BLENDER):
        print(f"  ⚠️ Debian 里的 blender 现在是 {bv}，组件说明写的是 {EXPECT_BLENDER}："
              f"照装，实际版本以 blender --selftest 的总结行为准")
    print(f"  依赖闭包：{len(order)} 个包 · 下载 {dl / 1048576:.0f} MB · 解开后约 {inst / 1024:.0f} MB")
    if missing:
        print(f"  ⚠️ 没解析到的名字 {len(missing)} 个（虚包/环境限定，通常无害）："
              f"{', '.join(missing[:6])}{' …' if len(missing) > 6 else ''}")

    plan = {"suite": SUITE, "roots": ROOTS, "packages":
            [{"name": n, "version": idx[n]["version"], "sha256": idx[n]["sha256"]} for n in order]}
    if os.path.isdir(root) and os.path.exists(marker):
        try:
            with open(marker, encoding="utf-8") as f:
                if json.load(f) == plan:
                    print(f"  已经装过，内容一致：{root}")
                    return 0
        except (OSError, ValueError):
            pass

    if dry:
        print(f"  （--dry-run：没下载。目标：{root}）")
        return 0

    # 目标目录可能还不存在；向上一层找最近的已存在目录再算空间
    # （直接 statvfs("/") 在安卓上恒为 0 —— 根分区对我们只读）
    probe = base
    while probe and not os.path.isdir(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    st = os.statvfs(probe or ".")
    free_mb = st.f_bavail * st.f_frsize / 1048576
    need_mb = inst / 1024 * 1.3
    if free_mb < need_mb:
        print(f"  ✗ 空间不够：剩 {free_mb:.0f} MB，需要约 {need_mb:.0f} MB", file=sys.stderr)
        return 1

    os.makedirs(root, exist_ok=True)
    os.makedirs(cache, exist_ok=True)
    print(f"  装到：{root}")
    print(f"  缓存：{cache}（.deb 留着，重装/续传不用再下）")

    t0 = time.time()
    # ── 下载：每个都核对索引里的 SHA256 ─────────────────────────────
    prog = {"n": 0}
    errors = []

    def fetch(name):
        p = idx[name]
        dest = os.path.join(cache, os.path.basename(p["filename"]))
        if not (os.path.exists(dest) and sha256_file(dest) == p["sha256"]):
            blob = http_get(mirror + p["filename"], timeout=600)
            got = hashlib.sha256(blob).hexdigest()
            if got != p["sha256"]:
                errors.append(f"{name}: SHA256 不符（索引 {p['sha256'][:16]}… / 实得 {got[:16]}…）")
                return None
            tmp = dest + ".part"
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, dest)
        with LOCK:
            prog["n"] += 1
            if prog["n"] % 25 == 0 or prog["n"] == len(order):
                print(f"    下载并核对 {prog['n']}/{len(order)}（{time.time() - t0:.0f}s）")
        return name, dest

    print("  ▸ 下载并核对 SHA256 …")
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        debs = [r for r in ex.map(fetch, order) if r]
    if errors:
        for e in errors:
            print("  ✗ " + e, file=sys.stderr)
        return 1

    # ── 解包 ────────────────────────────────────────────────────────
    print("  ▸ 解包 …")
    t1 = time.time()
    stats = {"files": 0, "links": 0, "skipped": 0}
    prog2 = {"n": 0}

    def unpack(item):
        name, deb = item
        with open(deb, "rb") as f:
            blob = f.read()
        try:
            extract_deb(blob, root, stats)
        except Exception as e:                                     # noqa: BLE001
            errors.append(f"{name}: 解包失败 {e}")
        with LOCK:
            prog2["n"] += 1
            if prog2["n"] % 25 == 0 or prog2["n"] == len(debs):
                print(f"    解包 {prog2['n']}/{len(debs)}（{time.time() - t1:.0f}s）")

    with ThreadPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(unpack, debs))
    if errors:
        for e in errors:
            print("  ✗ " + e, file=sys.stderr)
        return 1

    with open(marker, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    print(f"  完成：{len(debs)} 个包 · {stats['files']} 个文件 · {stats['links']} 条链接"
          f" · 跳过 {stats['skipped']} · 共 {time.time() - t0:.0f}s")
    print(f"  Blender 在：{root}/usr/bin/blender")
    return 0


if __name__ == "__main__":
    sys.exit(main())
