# 架构图

本目录的三张图用 **[Archify](https://github.com/tt-a1i/archify)** 生成 ——
从一份小体量的 JSON 规格渲染成可交互的自包含 HTML，再抽取成静态 SVG 供 README 内联展示。

| 图 | 类型 | 讲什么 |
|---|---|---|
| [开发闭环](dev-loop.svg) | architecture | 从程序化建模到装回本机，五步全在同一台平板上 |
| [GPU 渲染链路](gpu-chain.svg) | architecture | Blender → EGL → Zink → Turnip → KGSL → Adreno |
| [渲染调用序列](render-sequence.svg) | sequence | 一次 EEVEE 渲染的完整往返 |

## 三种格式，各有用途

| 格式 | 文件 | 用途 |
|---|---|---|
| **SVG** | `*.svg` | 静态矢量，README 内联显示，GitHub 直接渲染 |
| **HTML** | `*.html` | 可交互版本：缩放、搜索、聚焦、关系追踪、明暗主题、演示模式 |
| **JSON** | `*.json` | 规格本体 —— 改这个再重新渲染，图就更新了 |

交互版可以本地打开（例如 `python3 -m http.server` 后访问），
比静态图多出：点节点高亮关联路径、按类型筛选、三套引导章节（"完整链路 / 转译层 / 关键配置"）。

## 重新生成

安装 skill 后（见下方"来源"），在 skill 根目录执行：

```sh
# 1) 先校验（showcase 要求 9 项检查全过、0 错误 0 警告）
node bin/archify.mjs validate architecture dev-loop.json --quality showcase --json

# 2) 交付（冻结规格字节并原子写入 HTML，返回双哈希）
node bin/archify.mjs deliver architecture dev-loop.json dev-loop.html --quality showcase --json

# 3) 抽静态 SVG
node extract-svg.mjs dev-loop.html dev-loop.svg dark
node check-svg.mjs dev-loop.svg
```

### 交付哈希（可核验）

| 图 | specification sha256 | artifact sha256 |
|---|---|---|
| dev-loop | `c2bc357c49f6e9fc…` | `9d76e88efd2631d2…` |
| gpu-chain | `9e421a8a3b60fa84…` | `1739a6a7ca02b98e…` |
| render-sequence | `d1dc6d68f421f484…` | `85808b76dd05ea56…` |

> 改了 `.json` 之后必须重新 `deliver`，否则 HTML 里冻结的规格快照会与文件不一致。

## 两个工具脚本

### `extract-svg.mjs` —— 从 HTML 抽出独立 SVG

Archify 的 HTML 用外部 CSS 类渲染，SVG 本身**不带样式**，直接抠出来会是一张白图。
这个脚本做三件事：

1. **过滤 CSS** —— 只保留 SVG 真正用到的类（181 KB → 38 KB）
2. **XML 合规化** —— HTML 允许无值属性（`<text data-detail-anchor x="1">`），
   XML 不允许，必须补成 `=""`。**不补的话浏览器直接报 XML 解析错误，整张图只剩边框。**
3. **锁定主题 + 补背景** —— GitHub 不认 CSS 变量切换，固定 `data-theme="dark"`
   并加一层背景矩形

### `check-svg.mjs` —— 静态检查

扫描无值属性与标签配对。跳过注释、CDATA、引号内内容和文本内容 ——
**这点很重要**：天真的正则会节点文字（`Blender`、`EEVEE`）当成属性名报一堆假阳性。

## 来源

图由 **[tt-a1i/archify](https://github.com/tt-a1i/archify)**（MIT，⭐72k）生成。
本仓库使用其 DeepSeek Harness 集成包
[`@tt-a1i/archify-dsh`](https://www.npmjs.com/package/@tt-a1i/archify-dsh) 的 Skill，
**未修改其任何代码**；生成物（JSON/SVG/HTML）遵循同样的 MIT 许可。

安装（需要 pnpm 的 DSH 插件管理器；本机没有 pnpm，是手动解包安装的）：

```sh
dsh plugin --profile web add @tt-a1i/archify-dsh@0.1.0
```
