# Changelog

## v1.0.0

首个版本：在 Android 设备上原生运行 Blender 无头 CLI，**并打通 GPU 加速渲染**。

### 能力

- Blender 4.3.2 / Python 3.13.5 运行于 Debian arm64 二进制 + Termux glibc 运行时
- **EEVEE GPU 渲染** —— 比软件渲染快 **19 倍**（640×480: 1.75s vs 33.51s）
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
