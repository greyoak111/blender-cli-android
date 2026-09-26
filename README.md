# blender-cli-android

**在 Android 设备上原生运行 Blender 无头 CLI，并打通 GPU 加速渲染。**

无 root、无 Termux、无 Linux 发行版环境 —— 只用设备自身的 Android + 一个 glibc 兼容层。

```
$ blender --version
Blender 4.3.2

$ blender -b scene.blend -f 1          # EEVEE（GPU）
Time: 00:01.75

$ blender -b scene.blend -f 1          # Cycles（CPU）
Time: 00:01.21
```

---

## 成果

| 能力 | 状态 | 实测环境 |
|---|---|---|
| Blender CLI | ✅ 4.3.2 / Python 3.13.5 | Lenovo TB320FC |
| **EEVEE（GPU 渲染）** | ✅ **比软件渲染快 19 倍** | Adreno 730 / Vulkan 1.4.353 |
| **Cycles（CPU 渲染）** | ✅ 800×600@128 = 22.4s | 8 核并行 6.2x |
| glTF 导出 | ✅ | 可直接喂 Godot |
| 程序化资产生成 | ✅ Python API + 14 个内置插件 | |

### GPU 加速的证明

同一场景、同一分辨率（640×480），只切换 Mesa 的 Gallium 驱动：

| 后端 | 耗时 | |
|---|---|---|
| `llvmpipe`（纯软件） | **33.51 s** | |
| `zink`（GPU） | **1.75 s** | **19×** ✅ |

---

## 核心：GPU 链路是怎么打通的

```
Blender → EGL(Mesa surfaceless) → Zink(GL→Vulkan 转译)
        → Vulkan loader → Turnip(补丁版) → /dev/kgsl-3d0 → Adreno GPU
```

**四个缺一不可的环境变量：**

```sh
# 1) libglvnd 必须能找到 Mesa 的 EGL 厂商驱动 —— 没有它 eglinitialize 直接失败
export __EGL_VENDOR_LIBRARY_FILENAMES="$DEBROOT/usr/share/glvnd/egl_vendor.d/50_mesa.json"

# 2) 安卓没有 /dev/dri/*，只能用 surfaceless 平台
export EGL_PLATFORM=surfaceless

# 3) OpenGL → Vulkan 转译
export GALLIUM_DRIVER=zink
export MESA_LOADER_DRIVER_OVERRIDE=zink

# 4) Turnip 走 KGSL（不依赖被 SELinux 挡住的 DRM 节点）
export VK_ICD_FILENAMES=/path/to/patched_icd.json
```

> 第 1 条是最难的坎。缺了它只会看到 `EGL_BAD_PARAMETER` —— 一个**完全误导性**的报错。
> 详见 [docs/gpu-breakthrough.md](docs/gpu-breakthrough.md)

---

## 安装

### 前置

- Android 11+ arm64 设备
- 一个能运行 `node` 的环境（用于 `tools/` 下的脚本）
- 约 2.5GB 空闲存储
- 网络

### 步骤

```sh
# 1) glibc 运行时 + Vulkan 工具链
node tools/tpkg.mjs install glibc openjdk-17 \
  vulkan-tools-glibc mesa-vulkan-icd-freedreno-glibc vulkan-icd-loader-glibc

# 2) Debian arm64 的 Blender 依赖闭包（400+ 包，约 1.1GB）
node tools/debtool.mjs install blender python3-numpy

# 3) 补丁版 Mesa（关键！见下文「鸣谢」）
#    从 lfdevs/mesa-for-android-container 下载 debian_trixie_arm64 的 mesa 包
cd "$DEBROOT" && tar xzf mesa-for-android-container_*_debian_trixie_arm64.tar.gz

# 4) 生成 ICD 配置
sed "s|\\\$DEBROOT|$DEBROOT|" configs/patched_icd.json.template > /tmp/patched_icd.json

# 5) 运行
sh scripts/blender.sh --version
sh scripts/blender.sh -b --python script.py
```

`tools/debtool.mjs` 支持这些环境变量：

| 变量 | 说明 | 默认 |
|---|---|---|
| `DEB_PREFIX` | 解包目标 | `tools/debroot` |
| `DEB_SUITE` | Debian 套件 | `trixie` |
| `DEB_SKIP` | 跳过的包（默认跳过 `libc6`，用 Termux 的 glibc） | `libc6` |
| `DEB_CACHE` | `.deb` 缓存目录 | `tools/debcache` |

---

## 设计要点

### 为什么用 Debian 包而不是官方构建

Blender 官方**没有 Linux arm64 构建**（arm64 只给 macOS 和 Windows）：

```
blender-4.5.14-linux-x64.tar.xz        ← 只有 x64
blender-4.5.14-macos-arm64.dmg
blender-4.5.14-windows-arm64.zip
```

所以只能走发行版的 arm64 包。Debian trixie 有 `blender 4.3.2` ✓
它的 glibc 要求是 `>= 2.38`，而 Termux 的 glibc 是 **2.44**，满足。

### 为什么能混用

```
Termux glibc 2.44  →  提供 libc / ld.so（安卓上唯一能用的 glibc 运行时）
Debian 全套        →  提供 Blender 及其 400 个依赖
```

**但两者的库绝不能进同一个搜索路径** —— Termux 前缀里是 bionic 库
（符号版本是 `LIBC`/`LIBC_N`），一旦被优先命中就会报
`version 'LIBC' not found`。详见 [docs/pitfalls.md](docs/pitfalls.md) 第 5 条。

### 为什么不走 X11 路线

试过 Xvfb（虚拟 X 服务器）+ GLX，卡在：

```
Fatal server error: Could not create lock file in /tmp/.tX99-lock
```

`/tmp` 在安卓上属于 `shell` 用户且被 SELinux 保护，普通应用写不进去；
`-nolock` 又只允许 root。**最终发现 EGL surfaceless 平台 + Zink 才是正解。**

### 为什么必须用 Zink 而不是原生 GL 驱动

Freedreno 有原生 OpenGL 驱动（`msm`），但它需要 **DRM 节点**（`/dev/dri/renderD128`）。
实测该节点在本设备上**根本不存在**，只有 `/dev/kgsl-3d0`。
所以只能用 **Turnip**（走 KGSL）+ **Zink** 做 GL→Vulkan 转译。

---

## 已知限制

| 项 | 状态 | 说明 |
|---|---|---|
| Blender GUI | ❌ | 没有 X11/Wayland，只能 `-b` 无头模式 |
| Cycles GPU | ❌ | Blender 只支持 CUDA/OptiX/HIP/oneAPI/Metal，移动 GPU 均不支持 |
| 补丁版 Mesa 持久性 | ⚠️ | 后续安装任何 Debian 图形包会覆盖回发行版 Mesa，需重新解包 |

---

## 文档

| 文档 | 内容 |
|---|---|
| [docs/gpu-breakthrough.md](docs/gpu-breakthrough.md) | **GPU 打通全过程** —— 从 EGL 失败到 19 倍加速的完整排查 |
| [docs/pitfalls.md](docs/pitfalls.md) | 14 个坑的完整清单与根因分析 |
| [docs/background.md](docs/background.md) | 背景、方法论、以及为什么走这条路 |
| [docs/credits.md](docs/credits.md) | **鸣谢** —— 借鉴的开源项目 |

---

## 鸣谢

本项目的 GPU 部分**完全建立在别人的工作之上**，特别感谢：

- **[lfdevs/mesa-for-android-container](https://github.com/lfdevs/mesa-for-android-container)**
  —— 为安卓容器里的 Adreno GPU 打造的 Mesa 补丁版。**没有它，GPU 加速不可能实现。**
- **[alexvorxx/zink-xlib-termux](https://github.com/alexvorxx/zink-xlib-termux)**
  —— 提供了 Zink 在安卓上的构建参数，为 EGL 平台排查指明了方向。

完整鸣谢见 [docs/credits.md](docs/credits.md)。

## License

MIT（本仓库自身的脚本与文档）。
第三方组件遵循各自许可：Blender 为 GPL，Mesa 为 MIT，Debian 各包遵循其自身许可。
本仓库**不重新分发**这些二进制，只提供获取与配置的方法。
