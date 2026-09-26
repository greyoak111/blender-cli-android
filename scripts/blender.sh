#!/system/bin/sh
# ─────────────────────────────────────────────────────────────────────
#  Blender 无头 CLI 启动包装器 —— 在 Android 上原生运行
#
#    GPU 链路: Blender → EGL(Mesa surfaceless) → Zink → Vulkan
#                      → Turnip(补丁版) → /dev/kgsl-3d0 → Adreno GPU
#
#  用法:
#    blender.sh --version
#    blender.sh -b scene.blend -f 1              # 渲染（EEVEE 走 GPU）
#    blender.sh -b --python script.py            # 跑 Python 脚本
#
#  ── 路径约定 ──────────────────────────────────────────────────────
#  默认路径与 tools/ 下两个安装脚本保持一致，**零配置即可运行**：
#
#      tools/debtool.mjs  →  tools/debroot       （Debian 用户空间）
#      tools/tpkg.mjs     →  tools/prefix        （glibc 运行时）
#
#  想装到别处，设 BLENDER_ENV 指到统一目录，并让安装脚本用同一目录：
#
#      export BLENDER_ENV=/data/mydir
#      TPKG_PREFIX="$BLENDER_ENV/prefix" node tools/tpkg.mjs install ...
#      DEB_PREFIX="$BLENDER_ENV/debroot" node tools/debtool.mjs install ...
#      sh scripts/blender.sh --version
#
#  也可单独覆盖：GLIBC_PREFIX / DEBROOT / ICD
# ─────────────────────────────────────────────────────────────────────

SELF_DIR=$(dirname "$0")
case "$SELF_DIR" in
  /*) : ;;
  *) SELF_DIR="$PWD/$SELF_DIR" ;;
esac
REPO=$(cd "$SELF_DIR/.." 2>/dev/null && pwd)

# 默认与安装脚本的默认位置对齐（见上方「路径约定」）
BASE="${BLENDER_ENV:-$REPO/tools}"
GLIBC_PREFIX="${GLIBC_PREFIX:-$BASE/prefix}"
DEBROOT="${DEBROOT:-$BASE/debroot}"
B="$DEBROOT"
A="$B/usr/lib/aarch64-linux-gnu"

if [ ! -x "$B/usr/bin/blender" ]; then
  echo "blender.sh: 找不到 Blender（$B/usr/bin/blender）" >&2
  echo "  请先跑：node tools/debtool.mjs install blender python3-numpy" >&2
  echo "  或设 DEBROOT 指向已安装的 Debian 用户空间。" >&2
  exit 1
fi

# ── 库搜索路径 ──────────────────────────────────────────────────────
# ⚠️ 绝不能把 bionic 库放进这里！
#    Termux 前缀的 lib/ 是 bionic（符号版本 LIBC / LIBC_N）
#    只有 lib/glibc/lib 才是 glibc。
#    混用会报满屏 `version 'LIBC' not found`。
#
# Debian 的库不止放一个目录：/usr/lib、blas/、lapack/、pulseaudio/ …
# 所以要扫一遍所有含 .so 的子目录。扫 400+ 个目录有开销，结果缓存复用。
LIBCACHE="$BASE/.libpath.cache"
if [ -f "$LIBCACHE" ] && [ "$LIBCACHE" -nt "$A" ]; then
  LIB=$(cat "$LIBCACHE")
else
  LIB="$A:$GLIBC_PREFIX/glibc/lib"
  for d in $(find "$B/usr/lib" "$B/lib" -type d 2>/dev/null); do
    case "$d" in *python3*|*lib-dynload*|*aarch64-linux-gnu) continue ;; esac
    ls "$d"/*.so* >/dev/null 2>&1 && LIB="$LIB:$d"
  done
  mkdir -p "$BASE" 2>/dev/null
  echo "$LIB" > "$LIBCACHE" 2>/dev/null
fi

# ── Blender 资源与 Python ───────────────────────────────────────────
# Debian 把资源拆到 /usr/share/blender，且 Python 用系统库。
# 注意 BLENDER_SYSTEM_PYTHON 要指向**安装根**，不是 lib 目录。
export BLENDER_SYSTEM_RESOURCES="$B/usr/share/blender"
export BLENDER_SYSTEM_PYTHON="$B/usr"

# ── GPU（四个条件缺一不可）────────────────────────────────────────
# 1) libglvnd 必须能找到 Mesa 的 EGL 厂商驱动。
#    缺了它只会看到误导性的 `EGL_BAD_PARAMETER` —— 这是最难的一个坎。
export __EGL_VENDOR_LIBRARY_FILENAMES="$B/usr/share/glvnd/egl_vendor.d/50_mesa.json"

# 2) 安卓没有 /dev/dri/*，只能用 surfaceless 平台（GBM / X11 均不可用）
export EGL_PLATFORM=surfaceless

# 3) OpenGL → Vulkan 转译
export GALLIUM_DRIVER=zink
export MESA_LOADER_DRIVER_OVERRIDE=zink

# 3b) 着色器缓存固定到持久目录。
#     不设的话缓存会落到默认位置（可能是只读或非持久路径），
#     每次渲染都要重新编译着色器 —— 实测冷 11.1s / 预热 9.8s。
export MESA_SHADER_CACHE_DIR="${MESA_SHADER_CACHE_DIR:-$BASE/shader-cache}"
mkdir -p "$MESA_SHADER_CACHE_DIR" 2>/dev/null

# 4) Turnip 走 KGSL（不依赖被 SELinux 挡住的 DRM 节点）。
#    补丁包自带的 ICD 写的是绝对路径 /usr/lib/...，在非标准根目录下无效，
#    这里生成一份路径修正过的。
#    **每次都重新生成**（成本极低）—— 否则重新解压 Mesa 或挪动 DEBROOT 之后
#    会一直沿用旧的、指向错误路径的那份。
ICD_SRC="${ICD:-$B/usr/share/vulkan/icd.d/freedreno_icd.aarch64.json}"
ICD_FIXED="$BASE/patched_icd.json"
if [ -f "$ICD_SRC" ]; then
  mkdir -p "$BASE" 2>/dev/null
  # 只替换路径开头的 "/usr/ → "$B/usr/，
  # 不能替换中间的 /usr/lib/ ，否则 aarch64-linux-gnu 会被重复拼接
  sed "s|\"/usr/|\"$B/usr/|g" "$ICD_SRC" > "$ICD_FIXED" 2>/dev/null
fi
# 用文件是否存在来判断，不用 ${VAR:-default} ——
# 后者在生成失败时仍会指向一个不存在的文件
if [ -f "$ICD_FIXED" ]; then
  export VK_ICD_FILENAMES="$ICD_FIXED"
elif [ -f "$ICD_SRC" ]; then
  export VK_ICD_FILENAMES="$ICD_SRC"
fi

exec "$GLIBC_PREFIX/glibc/lib/ld-linux-aarch64.so.1" \
  --library-path "$LIB" "$B/usr/bin/blender" "$@"
