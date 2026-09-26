# Changelog

## v1.1.1 —— 认领运行环境 + 修一个坏掉的安装命令

### 🐛 修复：tools/tpkg.mjs 在仓库里跑不起来

它 import 的是裸模块名 `"xz-decompress"`，但仓库里只有 `vendor/` ——
**按本仓库 README 走第一步就会 `ERR_MODULE_NOT_FOUND`。**

原因是当初把脚本拷进仓库时，**从没在这个仓库里跑过一次**（本地跑得通是因为有 node_modules）。
已改为与 debtool.mjs 一致的相对路径引用，并实测通过。

> 这是"改了没跑"这一类错误的又一例，与 pitfalls #16/#17/#18 同源。

### 📌 认领运行环境

补上了此前完全缺失的一环 —— 本项目**所有工作都是在一个 App 里完成的**，
但仓库里过去 0 处提及：

- README 顶部加「运行环境」说明
- [docs/credits.md](docs/credits.md) 新增**「运行环境（地基）」**一节，
  置于所有其他鸣谢之前，说明它提供了什么、本项目用它做了什么
- 鸣谢里指向配套工具集 [deepseek-harness-android-tools](https://github.com/greyoak111/deepseek-harness-android-tools)


## v1.1.0 —— 全套架构图

用 [Archify](https://github.com/tt-a1i/archify) 画了三张图，放进 [docs/diagrams/](docs/diagrams/)。

| 图 | 类型 | 讲什么 |
|---|---|---|
| [开发闭环](docs/diagrams/dev-loop.svg) | architecture | 从程序化建模到装回本机，五步全在同一台平板上 |
| [GPU 渲染链路](docs/diagrams/gpu-chain.svg) | architecture | Blender → EGL → Zink → Turnip → KGSL → Adreno |
| [渲染调用序列](docs/diagrams/render-sequence.svg) | sequence | 一次 EEVEE 渲染的完整往返（12 条消息） |

### 每张图三种形态

- **SVG**（约 55KB）—— README 内联显示
- **HTML**（约 620KB）—— 可交互：缩放 / 搜索 / 聚焦 / 关系追踪 / 明暗主题 / 引导章节
- **JSON**（4–6KB）—— 规格本体，改它再渲染

三张均通过 **9/9 检查、0 错误 0 警告**（showcase 级），交付返回规格与产物双哈希。

### 顺带填的两个坑

Archify 的 HTML 用外部 CSS 类渲染，**SVG 本身不带样式**，直接抠出来是白图。所以写了
`docs/diagrams/extract-svg.mjs`：

1. **过滤 CSS** —— 只保留 SVG 用到的类（181KB → 38KB）
2. **XML 合规化** —— HTML 允许无值属性（`<text data-detail-anchor x="1">`），
   **XML 不允许**。不补 `=""` 的话浏览器直接报解析错误，**整张图只剩边框没有文字**
3. **锁定主题 + 补背景** —— GitHub 不认 CSS 变量切换

第 2 条是**真的踩到了**：第一版 SVG 在浏览器里打开就是一堆 "Unexpected token inside
open tag"，节点全丢。另配 `check-svg.mjs` 做静态检查（扫描时要跳过引号内容与文本内容，
否则节点文字 `Blender`/`EEVEE` 会被当成属性名报一堆假阳性）。

### 📌 又一次"先验证再交付"

这次没有改代码，但仍然按老规矩做：**生成 → 浏览器实测 → 才发现 XML 错误**。
如果只看 `file` 命令说"是个 SVG"就交付，用户拿到的会是一张只有边框的图。


## v1.0.4 —— 缓存校验改为全覆盖（不在文档里留尾巴）

第四轮评审提到一个边缘情况：缓存是否过期只看 `$B/usr/lib` 和 `$A`，
所以新包若只在**更深一层的子目录**或 `$B/lib` 下加库，缓存察觉不到。
评审的建议是"很少碰到，在 README 提一句就够了"。

**但先量了一下，发现有更彻底的解法：**

| 操作 | 耗时 |
|---|---|
| 完整扫描 | ~420 ms |
| **`find -newer` 校验** | **~25 ms** |
| 读缓存 | ~14 ms |

拆解后发现**贵的不是 `find`，而是那 223 次 `ls` 子进程**：

| 拆解项 | 耗时 |
|---|---|
| 纯 `find` 遍历 | 25 ms |
| 223 次 `ls` 子进程 | 1527 ms |

→ 校验改用 `find "$B/usr/lib" "$B/lib" -type d -newer "$LIBCACHE"`，
**成本 ~25 ms（与读缓存几乎持平），却能捕获所有变化** ——
包括原先漏掉的"在已有子目录里新增库文件"（该变化只体现在子目录自身的 mtime 上）。

### ✅ 验证

```
首次运行（含扫描）        867 ms
再次（缓存校验）          463 ms
往已有子目录 pulseaudio/ 放一个 .so
再次                      875 ms   ← ✅ 正确判定过期并重扫
连续 3 次                  465 / 473 / 467 ms   ← 稳定在快路径
删掉缓存后                 915 ms → 442 ms
GPU 渲染                   Time: 00:06.90      ← 功能未受影响
```

### 📌 一点方法论

评审给的是"文档提一句"的务实的建议，但**先量一下成本**发现
存在一个既便宜又彻底的解法 —— 代价从 420ms 降到 25ms，边缘情况直接消失。

**"记录已知限制"和"消除已知限制"之间，差的就是一次测量。**


## v1.0.3 —— 三轮评审修正

第三轮评审指出 3 处，另有一处是评审**基于本文档的错误记述**提出的推断。

### 🐛 修正

- **库路径缓存忽略 `GLIBC_PREFIX`** —— 缓存里存的是整条 `LIB`（含 glibc 路径），
  但失效判断只看 `$DEBROOT/usr/lib/aarch64-linux-gnu`。
  改了 `GLIBC_PREFIX`、或新包往 `/usr/lib` 下加了子目录，都会继续用旧缓存**且不报错**。
  → 缓存里**只存 Debian 侧扫描结果**，glibc 路径每次运行现拼；
  失效判断同时看 `$DEBROOT/usr/lib`（新增子目录）和 `$A`（新增库）
- **ICD 写入非原子** —— 两个 Blender 同时启动时，可能有一个读到写了一半的 JSON。
  → 改为**先写临时文件再 `mv`**（同文件系统内原子），缓存文件同样处理

### 📝 文档修正

- **`CHANGELOG` 里把验证目录写成了 `/tmp/clean-repo`**，但**实际跑的是应用私有目录**（应用身份）。
  这导致评审合理推断"验证是用 shell 身份做的，绕开了 `/tmp` 限制"。
  一次有效的验证，被文档写得看起来无效。
  → 修正为实际路径，并**显式标注执行身份**。新增 pitfalls #18

### ✅ 验证（明确标注执行身份）

```
身份: uid=10361(u0_a361)  应用身份（非 shell）
目录: /data/user/0/…/repo-clean  应用私有目录（非 /tmp）

$ sh scripts/blender.sh --version
Blender 4.3.2                                          # 零配置

$ GLIBC_PREFIX=/…/fake-glibc sh scripts/blender.sh --version
blender.sh[137]: /…/fake-glibc/glibc/lib/ld-linux-aarch64.so.1: not found
                                                       # ✅ GLIBC_PREFIX 立即生效（缓存未拦）

$ ls tools/ | grep patched_icd
patched_icd.json                                       # ✅ 无 .tmp 残留（原子写入）
```

### 📌 同一模式已出现三次（pitfalls #16 / #17 / #18）

| # | 表现 |
|---|---|
| 16 | 结论说 `/tmp` 写不进，步骤却往 `/tmp` 写 |
| 17 | 三个组件的默认路径互不一致 |
| 18 | 文档写的路径 ≠ 实际跑的路径 |

**三次都不是知识错误，而是文档与实现/执行没有对齐。**

防御手段：**把实际执行过的命令原样粘进文档，而不是事后凭记忆"描述"一遍。**

### 🙏 关于评审

本轮起在 [docs/credits.md](docs/credits.md) 中记录三轮外部代码评审（Claude）的贡献。
评审也出现过两次错误推测（KGSL 权限、"Adreno 725" 成因），均经实测否定、未被写入。
**评审的价值在于提出值得验证的问题，而非"说的一定对"。**


## v1.0.2 —— 二轮评审修正

第二轮评审又指出 4 处，其中第 1 条与 v1.0.1 修的 `/tmp` 问题是**同一类错误**。

### 🐛 修正

- **【路径对不上，最严重】** 三个组件的默认路径互不一致：
  `debtool` → `tools/debroot`、`tpkg` → `tools/prefix`、
  而 `blender.sh` 去 `$HOME/blender-env/` 找，**README 全程没设这些变量**。
  按文档走必失败。
  → `blender.sh` 默认值改为与两个安装脚本对齐（相对仓库根），
  并给 `tpkg.mjs` 补上 `TPKG_PREFIX`。**零配置即可运行**。
  → 新增 pitfalls #17
- **`VK_ICD_FILENAMES="${ICD_FIXED:-$ICD_SRC}"` 兜底是死代码** ——
  `ICD_FIXED` 恒有值，即使文件没生成也会指向不存在的路径。
  → 改为 `[ -f "$ICD_FIXED" ]` 判断文件存在
- **ICD 只生成一次** —— 重新解压 Mesa 或挪动 DEBROOT 后会一直用旧的错误路径。
  → 改为**每次启动都重新生成**（成本极低）
- **每次启动扫 400+ 目录拼库路径** —— → 结果缓存到 `.libpath.cache` 复用

### ✅ 验证方式（这次是端到端做的）

在干净目录（**应用私有目录**，不是 `/tmp` —— 见下方说明）复制仓库、
只在默认位置放好数据目录，**不设任何环境变量**：

```
$ cd $APP_HOME/repo-clean && sh scripts/blender.sh --version   # 应用身份(uid=10361)
Blender 4.3.2                                    # ✅ 零配置

$ sh scripts/blender.sh -b --python render.py
Time: 00:07.38                                   # ✅ GPU 渲染

$ echo "{\"ICD\":{\"library_path\":\"/WRONG/STALE.so\"}}" > tools/patched_icd.json
$ sh scripts/blender.sh --version
$ grep library_path tools/patched_icd.json
  "library_path": ".../tools/debroot/usr/lib/.../libvulkan_freedreno.so"   # ✅ 自动修正
```

### 📌 关于"同类错误连犯两次"

pitfalls #16（往 `/tmp` 写）和 #17（路径默认值不一致）是**同一个模式**：
**"我这边能跑"被当成了"别人那边能跑"**。

两者都不是知识错误，而是缺少一次**以陌生人身份走一遍**的验证 ——
写文档的人知道所有隐含前提，读的时候大脑会自动补全。

防御手段只有一条：**在干净环境里、不设任何环境变量、严格按文档走一遍。**


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
