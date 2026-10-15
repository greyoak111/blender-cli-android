---
name: blender
description: 用户要在这台设备上做"类 AE"的合成/动效，或要出片、批量处理画面、跑 3D 渲染时用 —— 多层叠加、关键帧动画、加字幕、图片序列转视频/GIF、无头渲图，全部靠 Blender 4.3.2 的无头 CLI + bpy 脚本完成，不需要图形界面。
---

# Blender 4.3.2（无头 CLI，glibc 侧）

**先跑自检**（约 3 秒，真跑一层合成，出 12 帧 PNG + 一个 H.264 MP4）：

```sh
blender --selftest
# ===== 总结 ===== 合成=OK 输出=PNG+MP4 帧数=12 版本=4.3.2
```

`blender --where` 看装在哪、装没装。

## 第一次用：要先装（**先问用户**）

```sh
blender --setup            # 从 Debian 官方仓库取 404 个包，逐个核对 SHA256
blender --setup --dry-run  # 只算体积，不下载
```

- **多大**：约 **267 MB 下载 / 1.1 GB 解开**（Blender 官方没有 Linux arm64 构建，只能走 Debian arm64 的包）。
- **从哪下**：`deb.debian.org`（trixie/arm64，只有这一个来源；`libc6` 跳过，用本机 glibc）。
- **装到哪**：`~/.cccodroid/blender/data/`（应用私有目录，不碰系统分区）；`.deb` 缓存留在 `data/debcache`，267 MB，可删。
- 装完不用再装；重复跑 `--setup` 会认出"内容一致"直接跳过。

⚠️ **跑之前先告诉用户体积并征得同意**（首次约 2~10 分钟，看网速）。没装过时直接跑自检或渲染，也会先触发这一步。

## 怎么跑

```sh
blender -b --factory-startup --python-exit-code 1 --python job.py
blender -b scene.blend -f 1                  # 渲染第 1 帧
blender -b --python-expr "import bpy; print(bpy.app.version_string)"
blender-run <Debian 程序> [参数...]           # 用同一套环境跑别的（python3、vulkaninfo…）
```

四个开关都是必须的：

| 开关 | 为什么 |
|---|---|
| `-b` | 无头。没有图形界面，`-b` 是唯一的运行方式 |
| `--factory-startup` | 不读用户配置，脚本行为可复现 |
| `--python-exit-code 1` | **不加这个，脚本里抛异常 Blender 也返回 0** —— AI 会以为成功 |
| `--python job.py` | 跑脚本（`-P` 同义） |

## 类 AE 合成：合成器节点 + 关键帧

合成器（Compositor）是 AE 那套：多层素材 → 各自变换 → 叠加 → 输出。节点名与关键帧写法：

```python
import bpy, os
scene = bpy.context.scene
scene.use_nodes = True
tree = scene.node_tree
tree.nodes.clear()

bg = tree.nodes.new("CompositorNodeImage");  bg.image = bpy.data.images.load("/sdcard/cccodroid/bg.png")
fg = tree.nodes.new("CompositorNodeImage");  fg.image = bpy.data.images.load("/sdcard/cccodroid/logo.png")

xf = tree.nodes.new("CompositorNodeTransform")     # 位置/旋转/缩放，等价 AE 的 Transform
for name, v1, v2 in (("X", -80.0, 80.0), ("Angle", 0.0, 6.28318), ("Scale", 1.0, 1.6)):
    s = xf.inputs[name]
    s.default_value = v1; s.keyframe_insert("default_value", frame=1)     # 关键帧 = 给输入插帧
    s.default_value = v2; s.keyframe_insert("default_value", frame=24)

blur = tree.nodes.new("CompositorNodeBlur"); blur.filter_type = "GAUSS"; blur.size_x = blur.size_y = 8
over = tree.nodes.new("CompositorNodeAlphaOver"); over.inputs[0].default_value = 1.0   # 透明叠加
comp = tree.nodes.new("CompositorNodeComposite")

tree.links.new(bg.outputs["Image"], over.inputs[1])
tree.links.new(fg.outputs["Image"], xf.inputs["Image"])
tree.links.new(xf.outputs["Image"], blur.inputs["Image"])
tree.links.new(blur.outputs["Image"], over.inputs[2])
tree.links.new(over.outputs["Image"], comp.inputs["Image"])
```

常用节点：`Image` / `MovieClip`（现成视频当素材）/ `RGB`（纯色）/ `Transform` / `Blur` / `Glare`（发光）/
`ColorBalance` / `AlphaOver`（上层盖上）/ `AlphaUnder` / `Mix` / `Mask` / `Composite`（最终输出前再套一次）。

**素材可以先程序生成**（不必有文件）：

```python
img = bpy.data.images.new("bg", width=320, height=240, alpha=True)
img.pixels.foreach_set([0.12, 0.25, 0.38, 1.0] * (320 * 240))   # 扁平 RGBA，行优先
img.update()
```

## 出片

```python
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 120
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = "/sdcard/cccodroid/out/f_"       # 前缀，自动补 0001、0002…
bpy.ops.render.render(animation=True)                    # 写序列
# 视频：内建 FFmpeg 编码，不用另外装编码器
scene.render.image_settings.file_format = "FFMPEG"
scene.render.ffmpeg.format = "MPEG4"                     # 容器
scene.render.ffmpeg.codec = "H264"                       # 编码
scene.render.ffmpeg.constant_rate_factor = "HIGH"        # 质量
scene.render.filepath = "/sdcard/cccodroid/out/clip"     # 给**不带扩展名**的路径
bpy.ops.render.render(animation=True)                    # → clip0001-0120.mp4
```

- 成品写到 `/sdcard/cccodroid/`（文件管理器可见、应用内能直接预览）。**输出目录要先建好**。
- 图片序列转 GIF / 拼图用本机自带的 ImageMagick：`magick -delay 8 -loop 0 f_*.png out.gif`。
- 只渲一帧用 `bpy.ops.render.render(write_still=True)` —— **少这个参数就不写文件**（见下）。

## 文字（标题/字幕）

合成器里**没有文字节点**。两条路：

1. **3D 文字对象**渲染成图，再当合成素材（推荐，效果最好）：
   ```python
   bpy.ops.object.text_add(); t = bpy.context.object
   t.data.body = "中文标题 ABC"
   t.data.font = bpy.data.fonts.load("/system/fonts/NotoSansCJK-Regular.ttc")  # 中文必须指定字体
   t.rotation_euler = (1.5708, 0, 0)      # 文字默认躺在 XY 平面朝 +Z，从正面拍要先立起来
   ```
   `/system/fonts/` 下还有 `NotoSansCJK-Bold.ttc` 等；不指定字体中文会是空白/方块。
2. 用 `magick -font … -annotate` 或 typst 先渲成 PNG，再用 `CompositorNodeImage` 贴上去。

## GPU

- Blender 的 EEVEE（3D 渲染）走 **EGL surfaceless → Zink → Turnip → KGSL**，组件已经配好；
  用 `blender --where` 能看到 glibc 根。实测（本机，Adreno）：1280×720/32 采样 **5.7 s（zink）vs 56.7 s（llvmpipe）**。
- 纯合成、编码、Python 批处理**不吃 GPU**，走 CPU（多核并行）。
- ⚠️ `--gpu-backend vulkan` **会崩**，别用。`/dev/dri` 存在不等于能用（SELinux 挡着，走的是 `/dev/kgsl-3d0`）。
- 想看 GPU 有没有生效：临时 `GALLIUM_DRIVER=llvmpipe blender …` 对比耗时。

## 坑（都是真踩过的）

| 现象 | 原因 / 怎么办 |
|---|---|
| 渲染"成功"了（返回 `FINISHED`、退出码 0）但**没有文件** | `bpy.ops.render.render()` 不加 `write_still=True` 不写盘 |
| 脚本报错但 `blender` 退出码还是 0 | 漏了 `--python-exit-code 1` |
| 打开文件/写临时文件报 `No such file or directory` | 安卓没有可写的根级临时目录。组件已把 `TMPDIR` 指到自己的数据目录；**你自己 fork 的进程要照抄这个 TMPDIR** |
| 中文变方块 / 空白 | 没给文字对象指定 `/system/fonts/NotoSansCJK-*.ttc` |
| 文字拍不到 | 文字默认躺在 XY 平面朝 +Z，正面拍要先 `rotation_euler=(1.5708,0,0)` |
| 输出的图位置不对/被裁 | `filepath` 对 PNG 是**前缀**（自动补 4 位帧号），对 FFMPEG 要**不带扩展名** |
| `No module named 'encodings'` | `BLENDER_SYSTEM_PYTHON` 得指向**安装根**（`…/usr`），不是 lib 目录；组件已设好 |
| 加载素材路径写相对路径失败 | 无头模式的工作目录不一定是你想要的；脚本里一律用绝对路径 |
| 写到 `/sdcard` 失败 | `/sdcard` 不能执行程序、不能建软链；只能当"输出/素材"目录用 |

## 实测数字（本机 NX769J / Android 14）

| 活 | 耗时 |
|---|---|
| 自检（320×240，2 层 + 关键帧 + 模糊，12 帧 PNG + 12 帧 MP4） | **2.2 s** |
| 关键帧合成出 PNG 序列（320×240 × 12 帧） | 2.1 s |
| 内建 FFmpeg 编 24 帧 H.264 MP4 | 1.9 s |
| 读现成 mp4 抽帧当素材（MovieClip 节点） | 1.7 s |
| EEVEE 1280×720/32 采样（GPU zink） | 5.7 s |
| 同上走 llvmpipe（纯 CPU） | 56.7 s |

## 要先问用户的事

- `blender --setup`：下载 267 MB（见上）。
- 覆盖或删除 `/sdcard/cccodroid/` 下已有文件之前，先问一句。
- 渲染大分辨率/长片段前报一下预计耗时和体积（10 秒 1080p 大约几十 MB）。
