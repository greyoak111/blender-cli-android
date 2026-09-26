# 鸣谢

**这个项目能成，GPU 部分完全建立在别人的工作之上。** 这里详细说明借鉴了什么、为什么关键。

---

## 运行环境（地基）

### 🌟 [woaiys3/deepseek-harness-android-app](https://github.com/woaiys3/deepseek-harness-android-app)

> *"DeepSeek Harness 手机版：可直接安装的 Android APK，AI 免 Root 操作手机
> （Shizuku/root 可选），文件编辑只需所有文件访问权限，前台保活 + AI 通知"*

**本项目的所有工作都是在它里面完成的。** 没有这个 App，下面所有项目都无从谈起 ——
它提供了 Shizuku 特权通道、文件访问、以及一个能在设备上跑起来的 DSH 运行时。

| 它提供的能力 | 本项目用它做了什么 |
|---|---|
| Shizuku 特权通道（uid=2000 shell） | 装 APK、读系统属性、截图、访问受保护目录 |
| 所有文件访问权限 | 直接读写 `/sdcard` 与应用私有目录 |
| 运行时可执行文件 | 跑 node、glibc 二进制、Blender / Godot |
| 前台保活 | 长时间渲染与编译不被打断 |

**⭐302 · MIT** —— 本仓库的软硬件前提。

---

## 决定性项目

### 🌟 [lfdevs/mesa-for-android-container](https://github.com/lfdevs/mesa-for-android-container)

> *"A Mesa build for containers on Android (PRoot, Chroot, LXC, Droidspaces, etc.),
> to support hardware acceleration with Adreno GPU."*

**⚠️ 一处更正（初版曾写"没有这个项目，GPU 加速不可能实现"，实测后证明这话说过头了）**

后续做对照测试发现：**Debian 发行版自带的 Mesa 25.0.7 也能跑通 EEVEE**，
所以补丁版 Mesa 并非严格必需。但补丁版确实明显更好：

| Mesa 版本 | Vulkan | 猴头场景 640×480（缓存预热） |
|---|---|---|
| Debian 原生 25.0.7 | 1.3.289 | 9.82 s |
| **补丁版 26.2.0-devel** | **1.4.353** | **6.53 s** |

**结论：补丁版快约 1.4 倍，且 Vulkan 版本更新。推荐使用，但不是硬性前提。**
（真正不可或缺的是 `__EGL_VENDOR_LIBRARY_FILENAMES`，见 [gpu-breakthrough.md](gpu-breakthrough.md)。）

**具体借鉴了什么：**

1. **补丁版 Mesa 二进制** —— 上游 Mesa 在安卓容器环境下跑 Adreno 有问题，
   这个项目专门做了修补。我们直接使用其 Debian trixie arm64 预编译包：
   ```
   mesa-for-android-container_26.3.0-devel-*_debian_trixie_arm64.tar.gz
   turnip_26.3.0-devel-*_debian_trixie_arm64.tar.gz
   ```
   实测**快约 1.4 倍**，Vulkan 从 1.3.289 升到 1.4.353。

2. **兼容性确认** —— 项目文档的兼容表明确列出
   **Adreno 710/720/722/730/732/735/740/750 → OpenGL / OpenGL ES / Vulkan 全部 Supported**。
   这让我们确认"这块 GPU 有戏"，从而值得继续投入排查。

3. **环境匹配** —— 它提供的正是 **Debian trixie arm64** 包，
   与我们的 Debian 用户空间完全对应，省掉了自己编译 Mesa 的巨大工作量。

**⭐ 343 · 59 forks** —— 如果你的设备也是 Adreno + 安卓容器场景，推荐直接用它。


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

### 🌟 [tt-a1i/archify](https://github.com/tt-a1i/archify)

> *"Agent skill for beautiful, verifiable architecture, workflow, sequence,
> data-flow, and lifecycle diagrams—self-contained HTML with motion and crisp export."*

**本仓库 [docs/diagrams/](diagrams/) 下的三张架构图由它生成。**

**具体借鉴了什么：**

1. **图本身** —— 开发闭环、GPU 链路、渲染序列三张图，
   及其可交互 HTML 与静态 SVG 两种形态
2. **"可验证"的设计** —— 校验器不只报错，还给出**可执行的修复建议**
   （例如"标签压在节点上，建议 `labelAt [773, 288]`"）。
   本仓库的文档风格也受益于这个思路
3. **规格与产物分离** —— JSON 是本体，HTML/SVG 是渲染结果，
   交付时冻结规格字节并返回双哈希，可核验

**⭐72k · MIT** —— 生成物同样遵循 MIT。

> 安装说明见 [docs/diagrams/README.md](diagrams/README.md)。
> 本仓库**未修改其任何代码**。

---

## 代码评审

本仓库的脚本与文档经过 **三轮外部代码评审（Claude）**，
累计发现 **12 处问题**，全部经核实后修正并入库。

| 轮次 | 发现 | 其中最有价值的一条 |
|---|---|---|
| 一审 | 5 处 | 安装步骤往 `/tmp` 写文件 —— 与本仓库 pitfalls #12 的结论**直接矛盾** |
| 二审 | 4 处 | 三个组件默认路径不一致 —— **按 README 操作必然失败** |
| 三审 | 3 处 | 库路径缓存忽略 `GLIBC_PREFIX`，改了也不失效且不报错 |

### 为什么这类贡献值得记录

上面这几条有一个共同特征：**作者自审时有结构性盲区。**

写文档的人知道所有的隐含前提（环境变量早就 `export` 过了、
`/tmp` 从来不用、路径早就配好了），**大脑会自动补全它们** ——
所以反复通读也读不出来。而评审者读的时候没有任何隐含前提。

这也是为什么 pitfalls 里 #16 / #17 / #18 三条**全是同一个模式**
（"我这边能跑"当成"别人那边能跑"），却都是由外部评审而非自审发现的。

### 评审意见也要验证

需要说明的是：评审过程中也出现过**两次错误推测** ——

- 认为 shell 身份拿不到 KGSL（实际 `/dev/kgsl-3d0` 是 666，普通应用可用）
- 认为 `vulkaninfo` 显示 "Adreno 725" 与驱动版本有关（实际两个版本都报 725）

两者都经实测否定，**没有被写进文档**。

> 记这一笔不是要贬低评审 —— 恰恰相反：
> **评审的价值在于"提出值得验证的问题"，而不在于"说的一定对"。**
> 收到意见就照单全收，和收到意见就一概不理，是同一种错误的两面。

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
| 18 个坑的记录 | 特别是「两套 C 运行时不能混」「EGL 报错误导」「文档↔实际不一致」三类通用陷阱 |
| 验证方法 | 用 A/B 性能对比证明 GPU 确实在工作；用干净环境验证零配置可用性 |

**方法论文档**（[gpu-breakthrough.md](gpu-breakthrough.md#方法论总结)）
可能比具体配置更有长期价值 —— 配置会过时，排查思路不会。

