"""blender 组件的自检：真跑一遍无头合成，出 PNG 序列 + H.264 MP4，验魔数。

跑法（由 `blender --selftest` 调起）：
    blender -b --factory-startup --python-exit-code 1 --python selftest.py

验的是「类 AE」那条链路：两层素材 → 合成器节点 → 关键帧动画 → 模糊 → AlphaOver
→ 合成输出 → PNG 序列 / 内建 FFmpeg 编码 MP4。全程不需要 GPU、不需要屏幕。

输出落在 $TMPDIR/blender-selftest/（env.sh 里 TMPDIR 指到组件数据目录）。
"""
import glob
import os
import sys
import time

import bpy

W, H, N = 320, 240, 12
# TMPDIR 由 lib/env.sh 设好（安卓没有可写的根级临时目录）；没设时退回前缀下的 tmp
TMP = os.environ.get("TMPDIR") or os.path.join(os.environ.get("PREFIX", os.getcwd()), "tmp")
OUT = os.path.join(TMP, "blender-selftest")


def make_image(name, pixels):
    img = bpy.data.images.new(name, width=W, height=H, alpha=True)
    img.pixels.foreach_set(pixels)
    img.update()
    return img


def main():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    for old in glob.glob(os.path.join(OUT, "f_*.png")) + glob.glob(os.path.join(OUT, "comp*.mp4")):
        os.remove(old)

    # ── 两层素材：底色 + 带透明通道的方块（程序生成，不依赖外部文件）──
    bg = make_image("selftest_bg", [0x20 / 255, 0x40 / 255, 0x60 / 255, 1.0] * (W * H))
    px = [0.0] * (W * H * 4)
    for y in range(H // 4, H * 3 // 4):
        row = y * W * 4
        for x in range(W // 4, W * 3 // 4):
            px[row + x * 4: row + x * 4 + 4] = [1.0, 0.8, 0.0, 1.0]
    fg = make_image("selftest_fg", px)

    # ── 合成器：Image ×2 → Transform（打关键帧）→ Blur → AlphaOver → Composite ──
    scene = bpy.context.scene
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()

    n_bg = tree.nodes.new("CompositorNodeImage")
    n_bg.image = bg
    n_fg = tree.nodes.new("CompositorNodeImage")
    n_fg.image = fg

    xf = tree.nodes.new("CompositorNodeTransform")
    for name, v1, v2 in (("X", -80.0, 80.0), ("Angle", 0.0, 6.28318), ("Scale", 1.0, 1.6)):
        s = xf.inputs[name]
        s.default_value = v1
        s.keyframe_insert("default_value", frame=1)
        s.default_value = v2
        s.keyframe_insert("default_value", frame=N)

    blur = tree.nodes.new("CompositorNodeBlur")
    blur.filter_type = "GAUSS"
    blur.size_x = blur.size_y = 6

    over = tree.nodes.new("CompositorNodeAlphaOver")
    over.inputs[0].default_value = 1.0

    comp = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(n_bg.outputs["Image"], over.inputs[1])
    tree.links.new(n_fg.outputs["Image"], xf.inputs["Image"])
    tree.links.new(xf.outputs["Image"], blur.inputs["Image"])
    tree.links.new(blur.outputs["Image"], over.inputs[2])
    tree.links.new(over.outputs["Image"], comp.inputs["Image"])

    # ── 输出设置 ───────────────────────────────────────────────────
    scene.render.resolution_x, scene.render.resolution_y = W, H
    scene.render.resolution_percentage = 100
    scene.render.fps = 12
    scene.frame_start, scene.frame_end = 1, N

    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = os.path.join(OUT, "f_")
    bpy.ops.render.render(animation=True)
    pngs = sorted(glob.glob(os.path.join(OUT, "f_*.png")))

    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.filepath = os.path.join(OUT, "comp")
    bpy.ops.render.render(animation=True)
    mp4s = sorted(glob.glob(os.path.join(OUT, "comp*.mp4")))

    # ── 校验：帧数 + 魔数 ──────────────────────────────────────────
    ok_png = len(pngs) == N and open(pngs[0], "rb").read(4) == b"\x89PNG"
    ok_mp4 = bool(mp4s) and b"ftyp" in open(mp4s[0], "rb").read(64)

    print(f"  合成器：2 层素材 + Transform 关键帧 + Blur + AlphaOver（{W}×{H} · {N} 帧）")
    if pngs:
        print(f"  PNG 序列 {len(pngs)}/{N} 帧 → {pngs[0]}（{os.path.getsize(pngs[0]) // 1024} KB）")
    if mp4s:
        print(f"  H.264 MP4 → {mp4s[0]}（{os.path.getsize(mp4s[0]) // 1024} KB）")
    print(f"  耗时 {time.time() - t0:.1f}s · Blender {bpy.app.version_string}")

    if not (ok_png and ok_mp4):
        print(f"===== 总结 ===== 合成=失败 PNG={len(pngs)} MP4={len(mp4s)}"
              f" 版本={bpy.app.version_string}", file=sys.stderr)
        return 1
    print(f"===== 总结 ===== 合成=OK 输出=PNG+MP4 帧数={N} 版本={bpy.app.version_string}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
