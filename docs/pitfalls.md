# 踩坑清单

在 Android 上跑通 Blender 的过程中踩过的 14 个坑，按实际遇到顺序排列。
每一条都包含**现象、根因、解法**，以及为什么值得记下来。

---

## 1. `libspnav.so.0: cannot open shared object file`

**现象**：Blender 启动即报缺库，但该包明明已经装进依赖闭包了。

**根因**：Debian 的库**不一定放在多架构目录**。`libspnav0` 把库放在
`/usr/lib/` 而不是 `/usr/lib/aarch64-linux-gnu/`。

**解法**：搜索路径补上 `$DEBROOT/usr/lib`。

> **教训**：Debian 的库目录布局不止一种。写死单一路径必然踩坑。

---

## 2. `libm.so: invalid ELF header`

**现象**：
```
find library=libm.so [0]; searching
  trying file=.../glibc/lib/libm.so
error: .../libm.so: invalid ELF header
```

**根因**：glibc 里的 **`libm.so` 是一个链接脚本（文本文件）**，内容是：
```
INPUT(libm.so.6)
```
那是给**链接器**（ld）用的，不是给**动态加载器**（ld.so）用的。
但某个 Debian 库的 `DT_NEEDED` 里写的是 `libm.so` 而非 `libm.so.6`，
动态加载器就把它当 ELF 读了。

**解法**：把这类链接脚本替换成指向真实库的符号链接：

```sh
mv libm.so libm.so.script.bak
ln -s libm.so.6 libm.so
```

同样的还有：`libc.so`、`libgcc_s.so`、`libtic.so`、`libtinfo.so`。

> **教训**：`.so` 和 `.so.N` 是两套完全不同的东西 —— 前者面向开发，后者面向运行。

---

## 3. `libdl.so: cannot open shared object file`

**现象**：修好 `libm.so` 后，接着要 `libdl.so`。

**根因**：glibc 2.34+ 把 `libdl`、`libpthread`、`librt` 合并进了 `libc`，
只保留 `libdl.so.2` 这样的兼容桩，没有 `libdl.so` 这个短名。

**解法**：补上短名符号链接：
```sh
ln -s libdl.so.2 libdl.so
ln -s libpthread.so.0 libpthread.so
ln -s librt.so.1 librt.so
```

> 这是坑 2 的同类问题，只是这次连 `.so.N` 都要手动挑。

---

## 4. `liblapack.so.3: cannot open shared object file`

**现象**：包已安装，但运行时找不到。

**根因**：Debian 用 **alternatives 机制**管理 BLAS/LAPACK 实现，
真实文件在子目录里：
```
usr/lib/aarch64-linux-gnu/blas/libblas.so.3
usr/lib/aarch64-linux-gnu/lapack/liblapack.so.3
```
而 `libblas.so.3` 这个"标准名"是由包安装脚本（postinst）**运行时创建**的 ——
我们只解包，不跑脚本，所以没有。

**解法**：把这两个子目录加进搜索路径。

> **教训**：只解包 `.deb` 会漏掉 `postinst` 脚本做的事（符号链接、alternatives、
> 缓存更新等）。

---

## 5. `version 'LIBC' not found` ⭐ 最有价值的一个

**现象**：一屏一屏的报错，但每个都长这样：
```
libc.so.6: version `LIBC' not found (required by .../libpulse.so.0)
libc.so.6: version `LIBC_N' not found (required by .../libpulsecommon-17.0.so)
```

**根因**：**把安卓 bionic 的库混进了 glibc 的搜索路径。**

`LIBC` / `LIBC_N` 是 **bionic 的符号版本命名**，而 glibc 用的是
`GLIBC_2.17`、`GLIBC_2.34` 这种。两者的版本表完全不同。

我们的 Termux 前缀（`$PREFIX/lib`）里全是 bionic 库。
为了给 Godot 提供 fontconfig 等依赖，那个目录一直在搜索路径里 ——
于是 Debian 二进制优先找到了 bionic 的 `libpulse.so.0`，
然后要求 bionic 风格的符号版本，自然对不上。

**解法**：**Blender 的搜索路径里绝不能出现 bionic 库目录。**

```sh
# ❌ 错误
LIB="$P/glibc/lib:$P/lib:$DEBROOT/usr/lib/aarch64-linux-gnu"

# ✅ 正确：只用 glibc 运行时 + Debian 的库
LIB="$DEBROOT/usr/lib/aarch64-linux-gnu:$P/glibc/lib:..."
```

> **教训（最重要的一条）**：**两套 C 运行时绝不能混用。**
> 判断某个库属于哪一套很简单 —— 看它的符号版本是 `GLIBC_*` 还是 `LIBC*`。
>
> 顺带一提：Termux glibc 仓库里的包（`*-glibc`）放的是 **glibc 版**，
> 位置在 `$PREFIX/glibc/lib`，和 `$PREFIX/lib` 里的 bionic 包是分开的。
> 混淆这两者就是这个坑的来源。

---

## 6. `libpulsecommon-17.0.so: cannot open shared object file`

**现象**：修完坑 5 后，接着缺这个。

**根因**：又是子目录布局 —— PulseAudio 的私有库在
`usr/lib/aarch64-linux-gnu/pulseaudio/`。

**解法**：不再手写路径，改成**自动收集所有含 `.so` 的子目录**：

```sh
LIB="$GLIBC"
for d in $(find "$DEBROOT/usr/lib" "$DEBROOT/lib" -type d); do
  case "$d" in *python3*|*lib-dynload*) continue ;; esac
  ls "$d"/*.so* >/dev/null 2>&1 && LIB="$LIB:$d"
done
```

> **教训**：与其一个个补，不如一次性把规则写对。

---

## 7. `fonts data path not found` / `Font data directory "fonts/" could not be detected!`

**现象**：Blender 启动正常但找不到字体，界面/文字渲染缺资源。

**根因**：Debian 把 Blender **拆包**了：
- `blender` —— 可执行文件
- `blender-data` —— 资源文件，装在 `/usr/share/blender/`

而我们的"根目录"是 `$DEBROOT` 不是 `/`，Blender 找不到这些资源。

**解法**：用环境变量显式指定：

```sh
export BLENDER_SYSTEM_RESOURCES="$DEBROOT/usr/share/blender"
```

> 这个变量是 **Blender 4.2+ 新增的**（统一资源根），
> 老版本用的是 `BLENDER_SYSTEM_SCRIPTS` / `BLENDER_SYSTEM_DATAFILES` 分开指定。

---

## 8. `No module named 'encodings'` / `Internal error initializing Python!`

**现象**：
```
Unable to find the Python binary, the multiprocessing module may not be functional!
Internal error initializing Python!
Fatal Python error: Failed to import encodings module
```

**排查过程**：

先隔离测试 —— 直接跑 Debian 的 `python3.13`：
```
$ PYTHONHOME=$DEBROOT/usr python3.13 -c "import encodings; print('OK')"
✅ Python OK: 3.13.5
```

**Python 本身没问题，是 Blender 的问题。**

**根因**：Blender 会**重置** Python 的搜索路径（它按自己的逻辑设置 `PyConfig`），
`PYTHONHOME` / `PYTHONPATH` 都可能被覆盖。

**解法**：用 Blender 自己的变量，且**要指向 Python 的安装根目录**（不是 lib 目录）：

```sh
export BLENDER_SYSTEM_PYTHON="$DEBROOT/usr"        # ✅ 安装根（含 bin/ lib/）
# export BLENDER_SYSTEM_PYTHON="$DEBROOT/usr/lib/python3.13"   ❌ 不行
```

> **教训**：`xxx_SYSTEM_PYTHON` 这类变量，看名字像"Python 库目录"，
> 实际语义是"Python 安装前缀"。**先试根目录。**

---

## 9. `Failed to denoise, build has no OpenImageDenoise support`

**现象**：Cycles 渲染刚开始就中止，报降噪器不可用。

**根因**：Debian 的 Blender 构建**不包含 OpenImageDenoise**，
但 Cycles 的 **默认设置里降噪是开启的** → 直接报错退出。

**解法**：
```python
scene.cycles.use_denoising = False
```

> **教训**：发行版构建可能裁掉某些可选组件，而默认配置假设它们存在。

---

## 10. `ModuleNotFoundError: No module named 'numpy'`（glTF 导出挂掉）

**现象**：Blender 本身正常，但一用 glTF 导出就崩：
```
from .blender.exp import export as gltf2_blender_export
ModuleNotFoundError: No module named 'numpy'
```

**根因**：Debian 把 `python3-numpy` 放在 **Recommends**（推荐依赖）里，
而不是 `Depends`（硬依赖）。**依赖解析器只跟 Depends，所以不会拉它。**
但 glTF 导出器实际上离了 numpy 就跑不起来。

**解法**：手动装上：
```sh
node tools/debtool.mjs install python3-numpy
```

> **教训**：**依赖解析器要看 Recommends。**
> 发行版把"功能上必需但可延迟"的依赖放这里，自动解析会漏掉。

---

## 11. `libncursesw.so.6: file too short`

**现象**：一个库文件只有 24 字节。

**根因**：连锁问题 ——
```
libncursesw.so.6 -> libncursesw.so.6.6      （符号链接）
libncursesw.so.6.6  = 24 字节，内容是:
    INPUT(libncursesw.so.6)                  （链接脚本）
```
**指向自己的死循环。** 真实库缺失。

**解法**：移除这些坏链，让加载器回落到 Debian 侧的真实库：
```
$DEBROOT/usr/lib/aarch64-linux-gnu/libncursesw.so.6 -> libncursesw.so.6.5  ✅ 真 ELF
```

> 这是坑 2 的变种，但死循环的形式更隐蔽。

---

## 12. `Could not create lock file in /tmp/.tX99-lock`（Xvfb 路线）

**现象**：启动 Xvfb 虚拟 X 服务器失败。

**排查过程**：
```
$ ls -ld /tmp
drwxrwx--x 2 shell shell 40 ... /tmp        ← 属于 shell，模式 771
```

用 Shizuku（shell 身份）改权限：
```
$ chmod 777 /tmp
drwxrwxrwx ... /tmp                          ← 改成功了
$ touch /tmp/_test
Permission denied                            ← 我们的应用仍然写不进去
$ ls -Zd /tmp
u:object_r:shell_data_file:s0 /tmp           ← 根因：SELinux 标签
```

**尝试过的所有绕法**：

| 方法 | 结果 |
|---|---|
| `chmod 777 /tmp` | ❌ SELinux 仍然拦截 |
| Xvfb `-nolock` | ❌ `Warning: the -nolock option can only be used by root` |
| 换显示号 `:123` | ❌ 锁文件仍在 `/tmp` |
| `TMPDIR=...` | ❌ X 服务器的锁文件路径是**编译期**写死的 |
| 以 shell 身份跑 Xvfb | ❌ shell 读不了应用私有目录（同样的 SELinux 隔离） |

**结论**：放弃 X11 路线，回到 EGL surfaceless。

> **教训**：`chmod` 成功 ≠ 能访问。**安卓上 DAC 权限通过后还有 SELinux 这一关。**
> 用 `ls -Z` 看标签，别只看权限位。

---

## 13. `EGL Error (0x300C): EGL_BAD_PARAMETER` ⭐ 最有价值的第二个

**现象**：
```
EGL Error (0x300C): EGL_BAD_PARAMETER: One or more argument values are invalid.
blender: epoxy_get_proc_address: Assertion `0 && "Couldn't find current GLX or EGL context."' failed.
```

**这个报错极具误导性** —— 字面意思像"参数传错了"，
于是很容易陷入"换 EGL 平台参数"的死胡同：

| 尝试 | 结果 |
|---|---|
| `EGL_PLATFORM=surfaceless` / `device` / `drm` | ❌ 全部一样 |
| 换 Mesa 版本（Termux → Debian → 补丁版） | ❌ 全部一样 |
| `GALLIUM_DRIVER=zink` / `llvmpipe` | ❌ 全部一样 |

**真正的突破口是绕开 Blender 去测 EGL：**

```sh
$ eglinfo
EGL client extensions string:          ← 空！
eglinfo: eglInitialize failed
```

**"client extensions 为空"才是真线索** —— 正常情况下这里应该有一长串
`EGL_EXT_platform_base` 之类的扩展。空的意味着
**libglvnd 根本没找到任何 EGL 厂商驱动**。

查配置：
```json
// $DEBROOT/usr/share/glvnd/egl_vendor.d/50_mesa.json
{ "ICD": { "library_path" : "libEGL_mesa.so.0" } }     ← 相对路径
```

配置在、库也在，但 libglvnd 在默认路径（`/usr/share/...`）下找不到 ——
**因为我们的根目录是 `$DEBROOT`，不是 `/`。**

**解法**：
```sh
export __EGL_VENDOR_LIBRARY_FILENAMES="$DEBROOT/usr/share/glvnd/egl_vendor.d/50_mesa.json"
```

**验证**：
```
EGL client extensions string:
    EGL_EXT_platform_base, EGL_EXT_platform_device,
    EGL_MESA_platform_surfaceless, ...       ← 有了
```
然后 EEVEE 立刻渲染成功。

> **教训（最有价值的一条）**：
> **报错信息会骗人。** `EGL_BAD_PARAMETER` 看起来是参数问题，实际是资源找不到。
> 当直接症状反复指向死胡同时，**去找一个能独立复现该组件的工具**
> （这里是 `eglinfo`），拿到**干净的症状**再判断。
>
> 另外：`__EGL_VENDOR_LIBRARY_FILENAMES` 这类 **glvnd 路径变量**
> 是"把 Linux 图形栈搬到非标准根目录"时的通用解法，值得记住。

---

## 14. 补丁版 Mesa 被覆盖

**现象**：GPU 本来好好的，装了个 Debian 图形包之后又不行了。

**根因**：任何安装 Debian 图形相关包的操作
（如 `mesa-utils` 会依赖 `libegl-mesa0`）都会**覆盖回发行版自带的 Mesa**，
把补丁版冲掉。

**解法**：重新解包补丁版：
```sh
cd "$DEBROOT" && tar xzf mesa-for-android-container_*_debian_trixie_arm64.tar.gz
```

**验证补丁版是否在位**：
```sh
ls -l "$DEBROOT/usr/lib/aarch64-linux-gnu/libEGL_mesa.so.0.0.0"
# 474768 字节 且时间戳是补丁包的 → 补丁版
# 398952 字节                      → 发行版（被覆盖了）
```

> **教训**：手动覆盖安装的文件会被包管理器"修回去"。
> 要么记录来源，要么把补丁版放在独立目录并优先搜索。

---

---

## 15. 着色器缓存没有固定位置（性能坑）

**现象**：同一个渲染，第一次 11.07s，后面稳定在 9.82s —— 但换了环境后又变慢。

**根因**：Mesa 默认把着色器缓存写到某个"看起来合理"的位置，
在非标准根目录 / 只读路径 / SELinux 受限目录下会**写不进去**，
于是**每次渲染都要重新编译着色器**。

**解法**：显式固定到可持久写的目录：

```sh
export MESA_SHADER_CACHE_DIR="$BASE/shader-cache"
```

实测效果（猴头 640×480，补丁版 Mesa）：

| | 第 1 次 | 第 2 次 | 第 3 次 |
|---|---|---|---|
| 缓存已固定 | 7.19 s | 6.70 s | 6.53 s |

> **教训**：性能类问题先确认**缓存有没有生效**，再谈优化。
> 在非标准环境下，很多"默认位置"其实都是写不进去的。

---

## 16. 不要往 `/tmp` 写任何东西（本文档最初的自身错误）

**现象**：本文档 v1.0.0 的安装步骤第 4 步写着：

```sh
sed "..." configs/patched_icd.json.template > /tmp/patched_icd.json   # ❌
```

**而本文档第 12 条刚刚证明过普通应用写不进 `/tmp`。前后自相矛盾。**

这是被外部评审指出来的 —— 照 README 操作的人会直接卡在权限错误上。

**解法**：
- 改由 `scripts/blender.sh` **自动生成** ICD 到 `$BLENDER_ENV/patched_icd.json`
- README 里加显式警告

> **教训**：**写完文档要按自己的步骤走一遍。**
> 文档里的"结论"和"步骤"不一致，是很容易犯又很难自察的错 ——
> 因为写的时候两段是分开想的。让外部评审过一遍非常值得。


## 汇总

| 类别 | 坑号 | 共性问题 |
|---|---|---|
| **库路径布局** | 1, 4, 6 | Debian 的库不止放一个目录 |
| **`.so` vs `.so.N`** | 2, 3, 11 | 链接脚本 ≠ 动态库 |
| **两套 C 运行时** | 5 | bionic 与 glibc 绝不能混 |
| **非标准根目录** | 7, 8, 13 | 编译期路径假设 `/` 是根 |
| **发行版构建裁剪** | 9, 10 | 可选组件缺失 / Recommends 依赖 |
| **安卓安全模型** | 12 | SELinux 比 DAC 更靠后 |
| **包管理冲突** | 14 | 覆盖安装会被修回 |
| **缓存/持久化** | 15 | 默认缓存路径在非标准环境下不可写 |
| **文档自洽性** | 16 | 结论与步骤自相矛盾（需按步骤走一遍） |

**其中第 5 条和第 13 条是最有价值的** —— 它们分别对应
"两套运行时混用"和"报错误导"这两类通用陷阱。
