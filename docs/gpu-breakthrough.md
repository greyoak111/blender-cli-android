# GPU 打通全过程

> 从「EEVEE 不可用」到「GPU 跑通」的完整排查记录。
> 这份文档记录了**每一步的判断依据和排除过程**，而不只是最终答案。

---

## 起点：三个后端全部堵死

拿到 Blender 4.3.2 能跑之后，第一个问题是它能不能用 GPU。当时的结论是**全堵**：

| 后端 | 需要 | 当时的判断 |
|---|---|---|
| Cycles GPU | CUDA / OptiX / HIP / oneAPI / Metal | Adreno 一个都不支持 ❌ |
| Cycles OpenCL（≤2.93） | OpenCL | 厂商栈被 Android linker 命名空间挡死 ❌ |
| EEVEE | 桌面 OpenGL 4.3+ 或 Vulkan | 只有 GLES 3.2 ❌ |

**但 "EEVEE 不行" 这个结论下得太早了。** 下面是一步步推翻它的过程。

---

## 第一步：先摸清 GPU 家底

在做任何判断之前，先把设备真实的图形能力查清楚（而不是靠猜）：

```
GPU          : Adreno 730
OpenGL ES    : 3.2（驱动 V@0615.96，2025-02 构建）
Vulkan       : ✅ vulkan.adreno.so + 系统加载器
OpenCL       : ✅ /vendor/lib64/libOpenCL.so
```

**关键的一步是查设备节点权限：**

```
crw-rw-rw- 1 system system 507, 0 /dev/kgsl-3d0      ← 666，普通应用可读写 ✅
/dev/dri/renderD128                                    ← 不存在 ❌
/dev/dri/card0                                         ← 不存在 ❌
```

**这两个发现决定了后面整条路线：**

1. `/dev/kgsl-3d0` 可访问 → **有机会**
   （对比：`/dev/input` 那次权限是拒绝的，直接堵死）
2. `/dev/dri/*` 不存在 → **Freedreno 原生 GL 驱动（`msm`）用不了**，只能走 Vulkan + 转译

---

## 第二步：验证 OpenCL 是不是真的不通

在把希望寄托于转译层之前，先确认已知的替代路线是否可行。

写了个探针 `tools/clprobe.c`，用 `dlopen` 尝试加载厂商 OpenCL：

```c
h = dlopen("/vendor/lib64/libOpenCL.so", RTLD_NOW);
```

**普通应用身份：**

```
dlopen 失败: library ".../libOpenCL.so" needed or dlopened by ".../clprobe"
is not accessible for the namespace "(default)"
```

→ Android 的 **linker 命名空间隔离**，普通应用碰不到 `/vendor` 私有库。

**shell 身份：**

```
Segmentation fault (退出码 139)
```

→ dlopen 能过，但厂商 OpenCL 栈在这种用法下直接崩。

**结论：OpenCL 这条路彻底死了。** （而且 Blender 3.0 之后本来也移除了 OpenCL 支持。）

---

## 第三步：翻 Termux 仓库，发现转译栈

既然要走 Vulkan 转译，先看现成的东西：

```
mesa-vulkan-icd-freedreno    Turnip —— Adreno 的开源 Vulkan 驱动
mesa                         Mesa（含 Zink）
clvk                         OpenCL → Vulkan 转译
angle-android                GLES → Vulkan
vulkan-tools                 含 vulkaninfo
```

**但立刻发现一个致命问题：** Termux 的包都是 **bionic**（安卓 libc），
而 Blender 是 **glibc**（Debian）二进制 —— **两者不能互相 dlopen**。

于是去查 glibc 仓库，**找到了对应版本**：

```
mesa-vulkan-icd-freedreno-glibc   v24.2.6   8.7MB
mesa-glibc                        v24.2.6   118MB
vulkan-icd-loader-glibc                     764KB
```

**这一刻 GPU 就有了理论上的可能。** 装上一试：

```
$ vulkaninfo --summary
GPU0:  Turnip Adreno (TM) 725
       apiVersion = 1.3.289
       memoryHeaps[0].size = 11.14 GiB
       queueFlags = GRAPHICS | COMPUTE | TRANSFER
```

**一个 glibc 进程拿到了完整的 Vulkan 设备**，11GB 可寻址显存 —— 这证明 KGSL 通信是真的通的。

> **判断依据**：`memoryHeaps` 和 `queueFlags` 是需要实际驱动初始化才能查到的，
> 不是简单的库加载。这排除了"只是枚举了个空壳"的可能。

> **附：关于 "Adreno (TM) 725" 这个型号名**
>
> 本机内核报的其实是 **`Adreno730v3`**（平台 `taro`，SoC `SM8475`）：
> ```
> $ cat /sys/class/kgsl/kgsl-3d0/gpu_model
> Adreno730v3
> ```
> 但 Turnip 显示成 **725** —— 这是驱动的**设备名串**，不是硬件真相。
> 实测 Termux 版（Mesa 24.2.6）和补丁版（Mesa 26.2.0）**都报 725**，
> 所以这纯粹是命名问题，**不影响功能，也不是需要换驱动的原因**。
>
> 看到 725 不必担心，以 kgsl 的 `gpu_model` 为准。


---

## 第四步：EEVEE 尝试 —— 撞上 EGL

有了 Vulkan，自然想让 Blender 的 EEVEE 用上它。第一次尝试：

```
Couldn't open libEGL.so.1: cannot open shared object file
```

**这是一个重要的信号**：Blender 即使在 `-b` 后台模式，也会为 EEVEE 尝试创建 EGL 上下文。

装上 Mesa（含 `libEGL.so.1`）后：

```
EGL Error (0x300C): EGL_BAD_PARAMETER: One or more argument values are invalid.
blender: epoxy_get_proc_address: Assertion `0 && "Couldn't find current GLX or EGL context."' failed.
```

### 排除法：把所有能试的组合都试一遍

| 尝试 | 目的 | 结果 |
|---|---|---|
| `EGL_PLATFORM=surfaceless` | 无显示设备的离屏上下文 | ❌ |
| `EGL_PLATFORM=device` / `drm` | 指定设备 | ❌ |
| `GALLIUM_DRIVER=zink` | GL→Vulkan 转译 | ❌ |
| `GALLIUM_DRIVER=llvmpipe` | **纯软件 GL**，排除 GPU 因素 | ❌ |

**最后一行是关键判断依据**：连纯软件渲染都失败，说明问题**不在 Zink、不在 GPU、不在 Turnip**，
而是 **EGL 上下文创建本身就不通**。

---

## 第五步：走出去找答案（转折点）

自己猜不下去了，去搜索这类场景的既有研究。找到两个直接对口的项目：

### [alexvorxx/zink-xlib-termux](https://github.com/alexvorxx/zink-xlib-termux)

它的构建参数揭示了**缺的是什么**：

```meson
-Dgallium-drivers=virgl,zink,swrast
-Dglx=xlib          ← GLX + Xlib
-Dplatforms=x11     ← X11 平台
```

作者在 **Adreno 630** 上用 X11 + Zink 跑通了 `glxgears` 和 WineD3D。

**这条线索让我判断：需要一个 X 服务器。** 于是去试 Xvfb。

### [lfdevs/mesa-for-android-container](https://github.com/lfdevs/mesa-for-android-container) ⭐343

> *"A Mesa build for containers on Android (PRoot, Chroot, LXC, Droidspaces, etc.),
> to support hardware acceleration with **Adreno GPU**."*

兼容表里 **Adreno 710/720/722/730** 明确标注 OpenGL / OpenGL ES / Vulkan **全部 Supported**，
而且提供 **Debian trixie arm64 的预编译包** —— 与我们环境完全匹配。

**这是决定性的外部资源。**

---

## 第六步：Xvfb 路线失败及原因

装 Xvfb 后：

```
Fatal server error:
Could not create lock file in /tmp/.tX99-lock
```

排查：

```
$ ls -ld /tmp
drwxrwx--x 2 shell shell 40 ... /tmp          ← 属于 shell
$ chmod 777 /tmp                              ← 用 Shizuku(shell) 改了权限
$ touch /tmp/_test
Permission denied                             ← 仍然不行
$ ls -Zd /tmp
u:object_r:shell_data_file:s0 /tmp            ← 是 SELinux 标签的问题
```

**排除过程：**
- `-nolock` 选项？→ `Warning: the -nolock option can only be used by root` ❌
- 换显示号？→ 锁文件仍在 `/tmp` ❌
- `TMPDIR`？→ X 服务器的锁文件路径是编译期写死的 ❌
- 以 shell 身份跑 Xvfb？→ **shell 读不了应用私有目录**（同样的 SELinux 隔离）❌

**结论：放弃 X11 路线，回到 EGL surfaceless。**

> 这个弯路没有白走 —— 正是"必须绕开 X11"这个约束，
> 让后面的排查方向收窄到了 EGL 本身。

---

## 第七步：找到真正的根因（突破）

回到 EGL。既然 Blender 的报错来自 libepoxy，那就**绕开 Blender 单独测 EGL**。
装了 `mesa-utils` 用 `eglinfo`：

```
EGL client extensions string:          ← 空的！
eglinfo: eglInitialize failed
```

**"EGL client extensions string 为空" 是决定性线索。**

正常情况下这里应该列出 `EGL_EXT_platform_base` 之类的扩展。
空的说明 **libglvnd 根本没找到任何 EGL 厂商驱动**。

于是查 libglvnd 的厂商配置：

```
$ find $DEBROOT -path "*glvnd*" -name "*.json"
/usr/share/glvnd/egl_vendor.d/50_mesa.json          ← 配置存在

$ cat 50_mesa.json
{ "file_format_version": "1.0.0",
  "ICD": { "library_path" : "libEGL_mesa.so.0" } }   ← 用的是相对路径
```

配置在，库也在，但 libglvnd **没有在默认路径下找到它** ——
因为我们的根目录是 `$DEBROOT`，不是 `/`。

**解法：显式告诉 libglvnd 去哪找。**

```sh
export __EGL_VENDOR_LIBRARY_FILENAMES="$DEBROOT/usr/share/glvnd/egl_vendor.d/50_mesa.json"
```

### 验证

```
EGL client extensions string:
    EGL_EXT_platform_base, EGL_EXT_platform_device,
    EGL_MESA_platform_surfaceless, ...              ← 有了！
```

然后 Blender：

```
Saved: 'render_eevee.png'
Time: 00:07.51
```

**EEVEE 渲染成功。**

---

## 第八步：证明它真的用了 GPU

渲染出图 ≠ 用了 GPU —— 它完全可能偷偷回落到软件渲染。**必须证明。**

### 方法一：读 GPU 利用率（失败）

```
/sys/class/kgsl/kgsl-3d0/gpu_busy_percentage     ← 读不到
```

### 方法二：A/B 性能对比（成功）

只切换 Gallium 驱动，**其余全部相同**（着色器缓存均已预热，各跑 3 次）：

| 场景 | `llvmpipe`（纯软件） | `zink`（GPU） | 加速比 |
|---|---|---|---|
| 默认立方体 640×480 | 33.51 s | 1.75 s | **19×** |
| 猴头 + 平滑着色 640×480 | 33.62 / 36.33 / 35.21 s | 7.09 / 6.92 / 7.01 s | **5.0×** |

**结论：GPU 确实在工作，加速比在 5–19 倍之间，取决于场景。**

> ⚠️ **踩过的坑：跨场景比较是错的。**
> 最初只测了立方体场景得到 19×，就把这个数字当成通用结论。
> 后来在同一文档里又测了猴头场景，得到 7s —— 如果不注明场景，
> 读者会以为两个数字矛盾，或者误以为 GPU 只有 5 倍提升。
>
> **加速比为什么会变**：软件渲染两个场景都约 34s（受填充率限制），
> 而 GPU 在几何/着色复杂的猴头场景上开销明显更高（1.75s → 7.01s）。
> 所以**任何性能数字都必须带上场景描述**。

> 这个 A/B 方法是本次排查里最有用的一招：
> 当无法直接观测 GPU 时，**对比"强制软件路径"和"目标路径"的性能**，
> 是最简单可靠的验证手段。

---

## 最终链路

```
Blender
  └─ EGL (Mesa surfaceless)          ← EGL_PLATFORM=surfaceless
      └─ Zink (OpenGL → Vulkan)      ← GALLIUM_DRIVER=zink
          └─ Vulkan loader
              └─ Turnip (补丁版)      ← VK_ICD_FILENAMES=patched_icd.json
                  └─ /dev/kgsl-3d0
                      └─ Adreno 730
```

**四个环境变量缺一不可，其中最难的是 `__EGL_VENDOR_LIBRARY_FILENAMES`。**

---

## 方法论总结

回头看，真正起作用的是这几条：

1. **先量化，再判断。** 一开始就查清了设备节点权限、GLES/Vulkan 版本、驱动文件，
   而不是凭"安卓只有 GLES"这种笼统印象下结论。

2. **用排除法缩小范围。** 「连纯软件 llvmpipe 都失败」这一步，
   直接把嫌疑从 GPU/Zink/Turnip 排除到了 EGL 本身。

3. **绕开出问题的组件去测底层。** Blender 的报错来自 libepoxy，
   就用 `eglinfo` 绕开 Blender 单独测 EGL —— 立刻拿到了干净的症状。

4. **读懂报错背后的含义。** `EGL_BAD_PARAMETER` 字面看是"参数错误"，
   实际是"找不到厂商驱动"。**"EGL client extensions 为空"这个间接症状才是真线索。**

5. **去搜别人怎么做的。** 卡住时不要硬钻 ——
   这类场景一定有人趟过，找到对口项目能省掉几天。

6. **证明你的结论。** "渲染成功"不等于"用了 GPU"，A/B 对比才能定论。

---

## 相关文档

- [pitfalls.md](pitfalls.md) —— 14 个坑的完整清单
- [background.md](background.md) —— 背景与整体思路
- [credits.md](credits.md) —— 鸣谢
