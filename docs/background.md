# 背景与工作思路

这份文档记录项目的来龙去脉、整体架构选择，以及可复用的工具设计。

---

## 一、为什么要做这件事

起点是一个很实际的问题：**只有一台安卓平板，能不能做 3D 内容创作？**

Blender 是程序化资产生成的核心工具 —— 它的 Python API 可以在无人值守的情况下
批量生成模型、导出 glTF、烘焙贴图。这些能力如果能跑在平板上，
就能和同样跑在平板上的 Godot 串成一条完整的**移动端资产管线**：

```
Blender(Python) → glTF → Godot → APK → 手机
```

但 Blender 官方的态度很明确 —— **没有 Linux arm64 构建**：

```
blender-4.5.14-linux-x64.tar.xz        ← 只有 x64
blender-4.5.14-macos-arm64.dmg         ← arm64 只给 macOS
blender-4.5.14-windows-arm64.zip
```

所以问题变成：**能不能让 x86 世界之外的 arm64 Linux 二进制在安卓上跑起来？**

---

## 二、整体架构：glibc 兼容层

安卓用的是 **bionic**（Google 自己实现的 C 运行库），
而所有 Linux 发行版的二进制都链接 **glibc**。这两者**二进制不兼容**。

所以需要一个 glibc 运行时 —— 我们用的是 **Termux 的 glibc 包**
（它是专门为在安卓上运行 glibc 程序而构建的）。

### 三层结构

```
┌─────────────────────────────────────────────────────────┐
│  第一层：glibc 运行时（Termux glibc 包）                  │
│    libc.so.6 / ld-linux-aarch64.so.1 / libm ...          │
│    ← 安卓上唯一能用的 glibc                             │
├─────────────────────────────────────────────────────────┤
│  第二层：Debian arm64 用户空间                            │
│    blender + 400 个依赖（libpython / ffmpeg / openexr…） │
│    ← 直接从 .deb 解包，不需要装发行版                     │
├─────────────────────────────────────────────────────────┤
│  第三层：图形栈                                           │
│    udev/DRM 不可用 → 走 Vulkan + Zink 转译               │
│    Turnip(补丁版) → /dev/kgsl-3d0 → Adreno               │
└─────────────────────────────────────────────────────────┘
```

### 关键约束：两层库不能混

第一层和第二层是**两套完全不同的 C 运行时环境**：

| | 第一层（Termux） | 第二层（Debian） |
|---|---|---|
| 内部还有 | `$PREFIX/lib` 是 **bionic** 库<br>`$PREFIX/glibc/lib` 才是 glibc | 全是 glibc |
| 符号版本 | `LIBC` / `LIBC_N`（bionic）<br>`GLIBC_2.17`（glibc） | `GLIBC_*` |

**所以搜索路径必须精确控制**：只放 `$PREFIX/glibc/lib` + Debian 目录，
**绝不能放 `$PREFIX/lib`**（那是 bionic 的）。

踩错这一步的表现是满屏 `version 'LIBC' not found` —— 详见 [pitfalls.md](pitfalls.md#5-version-libc-not-found-最有价值的一个)。

---

## 三、为什么用 Debian 包而不是别的方案

| 方案 | 评估 |
|---|---|
| **官方 Linux 构建** | ❌ 没有 arm64 |
| **自己编译 Blender** | ❌ 需要几小时，且要先编 400 个依赖 |
| **proot-distro 装完整发行版** | ⚠️ 可行但重，且是"装回一个 Linux"（用户明确不想要） |
| **直接解包 Debian arm64 包** ✅ | 轻量、可控、无需发行版环境 |

选最后一条。它需要一个工具：**能解析依赖闭包并把 .deb 解包到自有目录** ——
这就是 `tools/debtool.mjs` 的由来。

---

## 四、工具设计

### `tools/debtool.mjs` —— Debian 包管理器

不需要 root、不需要发行版环境，纯靠 HTTP + 解包：

```sh
node debtool.mjs install blender python3-numpy
node debtool.mjs size blender      # 只算闭包体积，不下载
node debtool.mjs list gcc          # 搜索
```

**工作流程：**

```
1. 拉取 Packages.gz 索引（main/contrib/non-free）
2. 解析依赖闭包（递归 Depends + Pre-Depends）
3. 跳过指定包（默认 libc6 —— 用 Termux 的 glibc）
4. 下载 .deb（带缓存）
5. 解包：ar → data.tar.xz → xz 解码 → tar 解包
```

**几个设计决策：**

- **跳过 `libc6`**：用 Termux 的 glibc 2.44（比 Debian 的 2.41 新，向后兼容）
- **保留其余全部**：`libstdc++6`、`libgcc-s1` 等都取 Debian 的，
  避免混用两套 C++ 运行时
- **内置 xz 解码器**：见下

### 为什么内置 `xz-decompress`

Termux/Debian 的 `.deb` 里是 `data.tar.xz`，而**安卓自带工具链里没有任何 xz 解压器**
—— 连 toybox 都没有：

```
xz ❌   unxz ❌   zstd ❌   lzma ❌       （toybox 里也都没有）
```

所以 `tools/vendor/xz-decompress/`（71KB，纯 JS/WASM 实现）**不是偷懒，
是物理上无法用系统工具替代**。

### `tools/tpkg.mjs` —— Termux 包管理器

同理，但面向 Termux 仓库（aarch64/bionic）。用于取：

- **glibc 运行时**（`glibc`，来自 `termux-glibc` 仓库）
- **glibc 版图形栈**（`vulkan-tools-glibc`、`mesa-glibc` 等）

支持多仓库（main + glibc），因为 glibc 包在独立仓库里。

### `tools/elfneed.mjs` —— ELF 依赖分析

读 `DT_NEEDED` / `PT_INTERP`，**不依赖 readelf**（安卓上没有）。
排查"缺哪个库"时非常有用 —— 我们用它一次性列出了全部 49 个直接依赖
和递归后的缺失项，比一个个试快得多。

### `tools/clprobe.c` —— OpenCL 探针

一个 60 行的 C 程序，用 `dlopen` 测试厂商 OpenCL 是否可用。
虽然最终结论是"不可用"，但它把这条路**确凿地排除**了，
避免了一直抱着侥幸心理。

> 这类"**证伪工具**"和"验证工具"一样重要 ——
> 花十分钟写个探针，比花两小时猜测划算得多。

---

## 五、方法论

几条在这次实践中反复起作用的做法：

### 1. 先量化，再判断

不要凭"安卓只有 GLES 所以不行"这种笼统印象下结论。
先查清楚：GPU 型号、驱动版本、设备节点权限、实际支持的 API。

**本次的例子**：一开始以为 GPU 完全没戏，
查完发现 `/dev/kgsl-3d0` 权限是 **666，普通应用可读写** ——
这个事实直接改变了整个可行性判断。

### 2. 用排除法缩小范围

当多个组件串联时，**逐段隔离**而不是整体猜测。

**本次的例子**：EEVEE 失败 → 试纯软件 llvmpipe 也失败 →
**立刻排除** GPU/Zink/Turnip 三个嫌疑，锁定到 EGL 本身。

### 3. 绕开出问题的组件，单独测底层

Blender 的报错来自 libepoxy，用它调试等于隔着一层。
换成 `eglinfo` 直接测 EGL，立刻拿到干净的症状
（`EGL client extensions string` 为空）。

### 4. 读懂间接症状

`EGL_BAD_PARAMETER` 是**误导性**的直接症状；
"client extensions 为空"才是**指向根因**的间接症状。

**当直接症状反复指向死胡同时，去找间接症状。**

### 5. 卡住时去找别人怎么做的

EEVEE 卡了很久，转折点是搜到两个对口项目
（见 [credits.md](credits.md)）。**这类场景一定有人趟过。**

### 6. 证明你的结论

"渲染成功" ≠ "用了 GPU"。用 A/B 对比（软件 vs GPU）拿到 19 倍差距，
才算真正验证。

### 7. 记录坑，而不只是记录答案

答案会过时，**踩坑的模式不会**。
本次的 14 个坑归纳成了 7 类通用问题（见 pitfalls.md 末尾的汇总表）。

---

## 六、相关项目

这套方法与工具不是孤立的 —— 同一批工具链还支撑着：

- **`godot-cli-on-android`** —— 在安卓上跑无头 Godot 并导出 APK
- 两者共享：glibc 兼容层思路、`tpkg`/`elfneed` 工具、以及"先量化再判断"的方法

组合起来形成完整的移动端开发闭环：

```
Blender(GPU) → glTF → Godot → APK → 发布
```

---

## 七、诚实的边界

| 限制 | 原因 |
|---|---|
| **Blender GUI 不可用** | 没有 X11/Wayland，且 `/tmp` 被 SELinux 保护（Xvfb 路线已试并排除） |
| **Cycles 不能用 GPU** | Blender 只支持 CUDA/OptiX/HIP/oneAPI/Metal，移动 GPU 均不在列 |
| **补丁版 Mesa 会被覆盖** | 后续安装 Debian 图形包会冲掉，需重新解包 |
| **依赖 Debian 包** | 官方无 arm64 构建，只能跟发行版的版本节奏 |

这些都是**架构性限制**，不是配置问题 —— 想突破需要在更底层动手
（比如给 Blender 写一个 Vulkan 计算后端，那是另一个量级的工程）。
