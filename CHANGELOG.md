# Changelog

## v1.0.1 —— 外部评审修正

感谢一位评审者指出的问题，本次修正了 5 处（含 1 处自相矛盾）：

### 🐛 修正

- **安装步骤往 `/tmp` 写文件** —— 与本文档 pitfalls #12 的结论直接矛盾
  （普通应用写不进 `/tmp`，SELinux 限制）。改为由 `blender.sh` 自动生成到 `$BLENDER_ENV/`。
  → 新增 pitfalls #16，教训是"**写完文档要按自己的步骤走一遍**"
- **性能数字口径不一致** —— 原首页把 EEVEE 与 Cycles 并排（场景/设置不同），
  且"19 倍"未标明场景。现改为**同场景 A/B 对照表**，并注明跨场景比较无意义
- **鸣谢中的夸大表述** —— 原文"没有 lfdevs 的补丁版 Mesa，GPU 加速不可能实现"
  经实测**不成立**：发行版 Mesa 25.0.7 也能跑通，补丁版快约 1.4 倍。已更正
- **未固定着色器缓存** —— 新增 `MESA_SHADER_CACHE_DIR`，否则每次重编译着色器。
  → 新增 pitfalls #15

### 📝 新增

- **"Adreno 725" 型号说明** —— Turnip 显示 725，内核实际是 `Adreno730v3`。
  实测两个 Mesa 版本**都报 725**，纯属驱动设备名串，不影响功能

### 📊 修正后的性能数据（同场景 A/B，缓存预热）

| 场景 | llvmpipe（软件） | zink（GPU） | 加速比 |
|---|---|---|---|
| 立方体 640×480 | 33.51 s | 1.75 s | 19× |
| 猴头 640×480 | 35.05 s | 7.01 s | 5.0× |

| Mesa 版本 | Vulkan | 猴头 640×480 |
|---|---|---|
| Debian 原生 25.0.7 | 1.3.289 | 9.82 s |
| 补丁版 26.2.0-devel | 1.4.353 | 6.53 s |


## v1.0.0

首个版本：在 Android 设备上原生运行 Blender 无头 CLI，**并打通 GPU 加速渲染**。

### 能力

- Blender 4.3.2 / Python 3.13.5 运行于 Debian arm64 二进制 + Termux glibc 运行时
- **EEVEE GPU 渲染** —— 同场景 A/B 对照：立方体 640×480 快 **19×**（1.75s vs 33.51s）；
  猴头 640×480 快 **5.0×**（7.01s vs 35.05s）。加速比随场景变化，跨场景比较无意义
- **Cycles CPU 渲染** —— 800×600@128 = 22.4s（8 核并行 6.2x）
- glTF 导出，可直接喂给 Godot
- Python 程序化资产生成

### 打通的 GPU 链路

```
Blender → EGL(Mesa surfaceless) → Zink(GL→Vulkan) → Turnip(补丁版)
        → /dev/kgsl-3d0 → Adreno GPU
```

关键突破点是 `__EGL_VENDOR_LIBRARY_FILENAMES` ——
缺了它只会看到误导性的 `EGL_BAD_PARAMETER`。

补丁版 Mesa 经实测**并非严格必需**（发行版 Mesa 25.0.7 也能跑，约慢 1.4 倍），
但 Vulkan 版本更新（1.4.353 vs 1.3.289），推荐使用。

### 工具

- `tools/debtool.mjs` —— Debian arm64 包管理器（依赖闭包解析 + 解包，无需 root）
- `tools/tpkg.mjs` —— Termux 包管理器（取 glibc 运行时与图形栈）
- `tools/elfneed.mjs` —— ELF 依赖分析（无需 readelf）
- `tools/clprobe.c` —— OpenCL 可用性探针
- `tools/vendor/xz-decompress` —— 内置 xz 解码器（安卓无任何 xz 工具）

### 文档

- `docs/gpu-breakthrough.md` —— GPU 打通全过程（含排查方法论）
- `docs/pitfalls.md` —— 14 个坑的完整清单与根因分类
- `docs/background.md` —— 背景、架构选择、工具设计
- `docs/credits.md` —— 鸣谢（**本项目 GPU 部分完全建立在他人工作之上**）

### 已知限制

- Blender GUI 不可用（无 X11/Wayland；Xvfb 路线已试并排除）
- Cycles 无法使用 GPU（Blender 仅支持 CUDA/OptiX/HIP/oneAPI/Metal）
- 补丁版 Mesa 会被后续 Debian 图形包安装覆盖
