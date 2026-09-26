# 鸣谢

**这个项目能成，GPU 部分完全建立在别人的工作之上。** 这里详细说明借鉴了什么、为什么关键。

---

## 决定性项目

### 🌟 [lfdevs/mesa-for-android-container](https://github.com/lfdevs/mesa-for-android-container)

> *"A Mesa build for containers on Android (PRoot, Chroot, LXC, Droidspaces, etc.),
> to support hardware acceleration with Adreno GPU."*

**没有这个项目，本仓库的 GPU 部分不可能实现。**

**具体借鉴了什么：**

1. **补丁版 Mesa 二进制** —— 上游 Mesa 在安卓容器环境下跑 Adreno 有问题，
   这个项目专门做了修补。我们直接使用其 Debian trixie arm64 预编译包：
   ```
   mesa-for-android-container_26.3.0-devel-*_debian_trixie_arm64.tar.gz
   turnip_26.3.0-devel-*_debian_trixie_arm64.tar.gz
   ```

2. **兼容性确认** —— 项目文档的兼容表明确列出
   **Adreno 710/720/722/730/732/735/740/750 → OpenGL / OpenGL ES / Vulkan 全部 Supported**。
   这让我们确认"这块 GPU 有戏"，从而值得继续投入排查。

3. **环境匹配** —— 它提供的正是 **Debian trixie arm64** 包，
   与我们的 Debian 用户空间完全对应，省掉了自己编译 Mesa 的巨大工作量。

**⭐ 343 · 59 forks** —— 如果你的设备也是 Adreno + 安卓容器场景，强烈建议直接用它。

---

### 🌟 [alexvorxx/zink-xlib-termux](https://github.com/alexvorxx/zink-xlib-termux)

**这个项目改变了排查方向。**

当时我们卡在 `EGL_BAD_PARAMETER`，反复尝试各种 `EGL_PLATFORM` 参数都无效。
读到它的 Mesa 构建参数后才意识到**缺的是什么**：

```meson
-Dgallium-drivers=virgl,zink,swrast
-Dglx=xlib          ← GLX + Xlib
-Dplatforms=x11     ← X11 平台
```

作者在 **Adreno 630** 上用 X11 + Zink 跑通了 `glxgears` 和 WineD3D，
证明了**安卓 + Zink + Adreno 这条路本身是通的**。

**具体影响：**

1. 让我们第一次确认"Zink on Adreno"是可行的，而不是理论空想
2. 提示了"平台（platforms）"是关键配置项 —— 由此展开对 EGL 平台的排查
3. 顺着这条线索我们才去试 Xvfb（虽然最终排除了 X11 路线，
   但正是"必须绕开 X11"这个约束把方向收窄到了 EGL 本身）

---

## 上游项目

### [Mesa 3D Graphics Library](https://gitlab.freedesktop.org/mesa/mesa)

提供了整套开源图形栈：

- **Turnip** —— Adreno 的开源 Vulkan 驱动（本项目的 GPU 通路核心）
- **Zink** —— OpenGL → Vulkan 转译层
- **Gallium** —— 驱动框架
- **libglvnd** / **EGL** / **GLX**

没有 Mesa 的开源驱动，安卓上的非特权应用基本没有可用的 GPU 通路。

### [Blender](https://www.blender.org/)

引擎本身。特别值得一提的是它在 **4.2+ 引入的
`BLENDER_SYSTEM_RESOURCES`** 变量 —— 正是这个变量让 Blender
能在非标准根目录下找到自己的资源（见 [pitfalls.md #7](pitfalls.md)）。

### [Debian](https://www.debian.org/)

提供了 arm64 的 Blender 及全部 400 个依赖包。
**没有 Debian 的 arm64 移植，这个项目无从谈起** —— 因为 Blender 官方不发 Linux arm64 构建。

### [Termux](https://termux.dev/)

提供了**安卓上唯一能用的 glibc 运行时**。
特别是 `termux-glibc` 仓库里的 `*-glibc` 系列包（Mesa、Vulkan 工具等），
是打通 GPU 的必要组件。

---

## 工具与库

| 项目 | 用途 |
|---|---|
| [xz-decompress](https://www.npmjs.com/package/xz-decompress) | 纯 JS/WASM 的 xz 解码器。**安卓自带工具链没有任何 xz 解压器**，这个依赖无法替代 |
| [toybox](https://landley.net/toybox/) | 安卓自带的命令行工具集（`tar` / `unzip` / `base64` 等） |
| [libepoxy](https://github.com/anholt/libepoxy) | Blender 使用的 GL 函数分发库（它的报错是本项目排查的重要线索） |

---

## 参考资料

排查过程中查证过的上游资料：

| 资源 | 用途 |
|---|---|
| [Blender issue #61164 — eevee can't render headless on cloud linux VM](https://projects.blender.org/blender/blender/issues/61164) | 确认无头 EEVEE 的既有困难 |
| [mesa-for-android-container issue #32](https://github.com/lfdevs/mesa-for-android-container/issues/32) | 其他人的 Adreno + Debian 容器实践 |
| [Godot issue #123504](https://github.com/godotengine/godot/issues/123504) | 关联项目 `godot-cli-on-android` 中遇到的 ETC2/ASTC 问题 |
| [vulkan-tools](https://github.com/KhronosGroup/Vulkan-Tools) | `vulkaninfo`，用于验证 Turnip 是否真的拿到了 GPU |

---

## 致谢方式

如果你因为本项目受益，**请优先去给上面两个决定性的项目点 star** ——
它们才是让 GPU 加速成为可能的关键：

- ⭐ [lfdevs/mesa-for-android-container](https://github.com/lfdevs/mesa-for-android-container)
- ⭐ [alexvorxx/zink-xlib-termux](https://github.com/alexvorxx/zink-xlib-termux)

本仓库只是把它们的成果**组装**成一条在安卓上跑 Blender 的完整路径，
并记录下组装过程中的所有坑。

---

## 本仓库的贡献

相对于上游项目，本仓库新增的是：

| 内容 | 说明 |
|---|---|
| `tools/debtool.mjs` | Debian arm64 包管理器 —— 解析依赖闭包并解包，无需 root / 发行版环境 |
| 完整链路文档 | Blender → EGL → Zink → Turnip 的**四条件**与排查方法 |
| 14 个坑的记录 | 特别是「两套 C 运行时不能混」与「EGL 报错误导」两类通用陷阱 |
| 验证方法 | 用 A/B 性能对比证明 GPU 确实在工作 |

**方法论文档**（[gpu-breakthrough.md](gpu-breakthrough.md#方法论总结)）
可能比具体配置更有长期价值 —— 配置会过时，排查思路不会。
