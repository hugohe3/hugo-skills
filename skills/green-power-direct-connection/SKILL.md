---
name: green-power-direct-connection
description: >
  绿电直连（新能源就近消纳）项目申报方案的编写参考：申报方案大纲框架一般包括哪些章节、每章论证什么；
  政策文件、参考报告和公开数据去哪里找；各章插图有哪些、可以从什么角度画（位置图、气候资源图、
  负荷与出力特性图、8760 h 运行图、规模比选图、电力系统接线图），并附可运行的参考作图脚本。
  适用于用户要编写、规划或补充绿电直连、就近消纳、源网荷储一体化直供类项目申报方案，
  询问大纲怎么搭、资料去哪找、图怎么画时。
---

# 绿电直连申报方案

申报方案要回答一个问题：这个负荷值得配这么多新能源和储能，配上以后能自己平衡、满足政策指标、经济可行、运行安全。本技能只提供三样东西，用到哪样读哪样：

| 需要什么 | 读什么 |
|---|---|
| 大纲怎么搭、每章论证什么、政策硬指标是多少 | [references/outline.md](references/outline.md) |
| 政策文件、参考报告、公开数据去哪里找，测算表怎么检查 | [references/source-materials.md](references/source-materials.md) |
| 各章有哪些图、可以从什么角度画、怎么画 | [references/figures.md](references/figures.md) |

## 使用方式

1. 先判断用户要哪一样。只问大纲就给大纲，只问资料就给资料来源，不必走完整流程。
2. 编写申报方案时，先按项目所在省取得正式编制大纲（新疆、江西等已有样本，见 `outline.md`），再对照 `source-materials.md` 列出缺哪些资料，向用户索取；不要编造缺失的数据。
3. 规划插图时，按 `figures.md` 里各类图的角度逐张挑选，不必全画。需要数据图时可以直接运行 `scripts/` 里的参考实现，也可以只借用其中的画法。
4. Word、PDF、Excel 转 Markdown 用 `markdown-conversion` 技能，影印版 PDF 用 `pdf-transcription`；场址范围叠加到卫星截图用 `geospatial-converter`；可编辑的电气主接线、调控平台架构图用 `diagram-creator`。
5. 没有指定输出位置时，按仓库约定放在 `projects/<YYYYMMDD>-<项目简称>/`，建议结构：`0-inputs/`（原始资料，只读）、`0-materials/`（转换稿、中间数据）、`1-drafts/`（各章 Markdown）、`2-figures/`（插图和图表数据）、`8-scripts/`（本项目的作图命令）。

## 参考实现

`scripts/` 下的脚本可独立运行，依赖见 [resources/requirements.txt](resources/requirements.txt)，参数模板见 [resources/params.example.json](resources/params.example.json)。

| 脚本 | 作用 |
|---|---|
| `prepare_hourly.py` | 把测算表和 PVsyst 逐时数据整理成标准 8760 h 数据并出指标摘要 |
| `make_figures.py` | 负荷、出力特性、运行情况、规模比选等数据图 |
| `make_context_figures.py` | 逐月气温降水和辐射图、电力系统接线示意图 |
| `make_site_map.py` | 由 KML 场址范围和负荷坐标画位置示意图 |
| `fetch_nasa_power.py` | 下载 NASA POWER 场址多年气候统计 |

各脚本的输入格式、命令和参数见 `figures.md` 第三节。

## 工作原则

- 业主备案的规模、负荷配置和厂址优先，报告负责论证支撑，不推翻；发现矛盾时告诉用户，由用户决定。
- 一个数字只有一个来源：电量、小时数、比例都从同一套逐时数据算出，财务指标取用户指定的测算表工作表；上游数据变了就重新出图，再回头改正文。
- 测算表按原样引用，发现公式错误先报告用户，同意后再修正并留痕。
- 正文是给评审看的：不写“经核对测算表”“我方认为”这类内部过程，不挑业主或政策文件的毛病；【待业主确认】只用于交付前需要业主补齐的事实。
- 结构跟随参考：用户给了格式参考或已有章节框架时，沿用其小节结构和叫法，新增要求并入最接近的原有小节。
