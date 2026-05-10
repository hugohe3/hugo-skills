---
name: learning-master
description: >
  六阶段学习助手，用于系统化学习课程、书籍和文章。
  生成学习计划、预习笔记、通读笔记、Anki 复习卡片和外化产出。
  当用户需要系统学习、制作学习笔记、生成 Anki 卡片或管理学习项目时使用。
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Learning Master

基于**六阶段学习法**的结构化学习技能。针对**已确定的课程或书籍**，引导用户从建立计划到最终产出。

```
建立计划 → 资源转换 → 预习 → 通读 → 内化 → 外化
    ↓          ↓        ↓       ↓       ↓       ↓
目录+规划   转为MD    框架梳理  深度笔记  Anki卡片  作品产出
```

## 命令速查

| 命令 | 说明 | 阶段 |
|------|------|------|
| `/study-init-course` | 创建学习项目（目录 + 计划 + 资源转换） | 建立计划 |
| `/study-step1-preview` | 生成预习笔记 | 预习 |
| `/study-step2-notes` | 生成详细通读笔记 | 通读 |
| `/study-step3-anki-review` | 生成 Anki 卡片并导出 TSV | 内化 |
| `/study-step4-output-works` | 生成外化建议与行动计划 | 外化 |
| `/study-run-full-flow` | 完整流程（预 → 通 → 内 → 外） | 全阶段 |
| `/study-step5-final-summary` | 课程结课总结 | 全阶段 |

---

## 通用约定

### 项目目录结构

```
projects/<课程名>/
├── plan.md                # 学习计划
├── summary.md             # 课程总结
├── 0-resources/           # 原始资源与转换后的 Markdown
├── 1-preview/             # 预习笔记
├── 2-notes/               # 通读笔记
├── 3-review/              # Anki 卡片（Markdown 格式，-3.md）
│   └── anki-export/       # Anki 导入文件（TSV 格式，-3-anki.txt）
├── 4-works/               # 外化产出
└── 9-archive/             # 归档
```

### 文件命名规则

| 阶段 | 后缀 | 示例 |
|------|------|------|
| 预习 | `-1.md` | `第1章-1.md` |
| 通读 | `-2.md` | `第1章-2.md` |
| 复习 | `-3.md` | `第1章-3.md` |
| 外化 | `-4.md` | `第1章-4.md` |

- **强制要求**：保留原文件名完整信息，仅添加阶段后缀
- 课程级文件（`plan.md`、`summary.md`）直接放在项目根目录
- 原始资源和转换后的 Markdown 统一放在 `0-resources/`

### 进度状态

| 状态 | 含义 |
|------|------|
| `⏳` | 尚未开始 |
| `🔄` | 正在学习中 |
| `📝` | 笔记已生成，待完成学习 |
| `✅` | 已完成学习 |

**强制规则**：
- 生成笔记后标记为 `📝`，**不能**直接标记为 `✅`
- 只有用户明确确认"已学完"，才能标记为 `✅` 并填写完成日期
- `plan.md` 是课程级进度的唯一记录点
- 章节状态更新要与对应产出目录保持一致

**更新时机**：
- 执行预习、通读、内化、外化后：更新为 `📝` 或 `🔄`
- 用户确认完成章节学习后：更新为 `✅`
- 完成课程总结后：补充结课日志

### 写作规范

- 使用**简体中文**，使用中文标点：，。！？：；""''
- 英文/代码内容使用英文标点
- 省略号使用 `……`（6 个点）
- 中英文之间加空格：`学习 Python 语言`
- 数字与中文之间加空格：`共 3 个步骤`
- 代码、文件名用反引号包裹
- 首次出现英文术语附中文：`Markdown（MD）`，后续使用统一形式
- 保留专有名词原文：GitHub、Python

### 文件冲突处理

当目标文件已存在时，先询问用户是**覆盖**还是**追加**。默认追加——在原文件末尾增加 `## 补充` 区块。

---

## 命令：/study-init-course

> 创建课程目录、学习计划，并完成资源准备。

### 步骤

1. **确认项目信息**——向用户询问：
   - 主题/名称（课程名、书名或文章标题）
   - 类型（在线课程、书籍、线下培训、公众号文章等）
   - 来源（平台、出版社或 URL）
   - 内容体量（总时长、页数或字数）
   - 时间安排（每天/每周投入时间，计划多久学完）
   - 学习动机（为什么学？想解决什么问题？）
   - 产出目标（学完后打算输出什么成果？）

2. **确认理解**——简要复述并确认项目名称

3. **创建目录结构并整理原始文件**
   ```bash
   mkdir -p "projects/<主题名称>/"{0-resources,1-preview,2-notes,3-review,4-works,9-archive}
   ```
   - **强制要求**：如果用户提供了原始资料（如 PDF、Word、视频等），必须将资料整理到 `projects/<主题名称>/0-resources/` 目录下；默认复制，只有用户明确要求整理源文件时才移动。

4. **生成学习计划**——参考模板 [templates/0-plan.md](templates/0-plan.md)，写入 `projects/<主题名称>/plan.md`
   - **三维审视**：分析关联性、价值性和目标性
   - **SMART 目标**：将模糊目标转化为可衡量的具体目标
   - **结构适配**：书籍按"章/节"、课程按"周/模块"、文章按"核心观点"

5. **资源转换**（如有原始资料）——调用 `markdown-conversion` skill 将资料转为 Markdown：
   - 文档类（Word/HTML/EPUB）→ Pandoc
   - 原生 PDF → 本地解析
   - 扫描版/复杂 PDF → MinerU
   - 字幕目录 → 字幕转换脚本
   - 详细见 [skills/markdown-conversion/SKILL.md](../markdown-conversion/SKILL.md)
   - 转换结果存入 `projects/<课程>/0-resources/`
   - 检查质量：无乱码、阅读顺序通顺

6. **后续**——资源准备完成后进入 `/study-step1-preview`

---

## 命令：/study-step1-preview

> 快速建立框架，带着问题进入深度学习。预习不求深，只求「知道会讲什么」，5-10 分钟/章。

### 步骤

1. **确认课程**——扫描 `projects/` 列出已有课程供用户选择，确认章节范围

2. **获取内容**——优先读取 `projects/<课程>/0-resources/` 中的内容

3. **生成预习笔记**——按模板 [templates/1-preview.md](templates/1-preview.md) 生成，包含：
   - 作者/讲师简介
   - 内容概览（2-3 句话）
   - 内容结构（树状图）
   - 核心概念表
   - 关键要点（3-5 条）
   - 预习问题（3 条）

4. **保存**——`projects/<课程>/1-preview/[原名]-1.md`

5. **后续建议**——可上传 NotebookLM 生成音频播客 → 进入 `/study-step2-notes`

---

## 命令：/study-step2-notes

> 深度理解内容，生成详细章节笔记。通读追求理解，学完一章要能解释给别人听。

### 步骤

1. **确认课程**——扫描 `projects/` 列出已有课程供用户选择，确认章节范围

2. **生成笔记**——按模板 [templates/2-notes.md](templates/2-notes.md) 生成：
   - **深度总结**，不是简单提取
   - 用自己的语言重新组织
   - 保留关键术语和定义
   - 每个知识点包含：定义、要点、示例
   - 标记重点，记录理解困难的地方

3. **保存**——`projects/<课程>/2-notes/[原名]-2.md`

4. **理解困难处理**——遇到不理解的概念，提供：简单解释 + 具体例子 + 实际应用场景

5. **后续**——建议进入 `/study-step3-anki-review`，尝试合上笔记回忆

---

## 命令：/study-step3-anki-review

> 把章节知识转成 Anki 卡片，并自动导出可导入的 TSV 文件。

### 卡片设计原则

- **一卡一点**：每张卡只测试一个知识点
- **先问后答**：正面是问题，背面是答案
- 每章输出 **10-20 张卡片**

### 卡片类型

| 类型 | 正面 | 示例 |
|------|------|------|
| 定义 | 什么是 X？ | 什么是费曼技巧？ |
| 对比 | X 和 Y 的区别？ | TCP vs UDP |
| 应用 | 如何用 X 解决 Y？ | 如何用 MECE 分析问题？ |
| 联结 | X 和 Y 的关系？ | OKR 和 KPI 的关系？ |
| 追问 | 为什么 X？ | 为什么要用依赖注入？ |
| 类比 | X 像什么？ | TCP 三次握手像什么？ |

### 卡片格式

```markdown
**Q**: [问题]
**A**: [答案]
---
```

按知识点类型分组（如 `## 概念类`），用 `---` 分隔每张卡片。

### 步骤

1. **确认课程**——扫描 `projects/` 列出已有课程供用户选择，确认章节范围

2. **读取**——优先读取 `projects/<课程>/2-notes/`

3. **生成卡片**——按模板 [templates/3-review.md](templates/3-review.md)

4. **标记薄弱点**——在文档底部的 `## 薄弱点` 记录反复忘记的概念

5. **保存 Markdown**——`projects/<课程>/3-review/[原名]-3.md`

6. **导出 TSV**——自动调用脚本生成 Anki 导入文件：
   ```bash
   python3 skills/learning-master/scripts/generate_anki_cards.py "projects/<课程>/3-review/[原名]-3.md"
   ```
   - 在其他项目中使用该技能时，先定位本技能目录，再调用其中的 `scripts/generate_anki_cards.py`
   - 输出文件：`[原名]-3-anki.txt`，保存在 `3-review/anki-export/` 目录下
   - TSV 格式：`Front内容<TAB>Back内容`
   - Markdown 会转换为 HTML；字段内物理换行转 `<br>`，Tab 转空格，避免破坏 TSV
   - 导入 Anki 时：允许 HTML，分隔符为 Tab

7. **后续**——进入 `/study-step4-output-works`

---

## 命令：/study-step4-output-works

> 将知识转化为实践。外化标准：「能教会别人」或「能解决实际问题」。

### 步骤

1. **确认课程**——扫描 `projects/` 列出已有课程供用户选择，确认章节范围

2. **读取**——`projects/<课程>/2-notes/` 和 `3-review/`

3. **推荐产出类型**——根据课程内容推荐 1-2 种具体产出：
   - 技术类 → 代码 demo / 技术博客大纲
   - 理论类 → 核心观点梳理 / 读书笔记文章框架
   - 技能类 → 实操 checklist / 练习计划
   - 通用 → 教别人用的讲解稿大纲

4. **生成产出框架**——按模板 [templates/4-works.md](templates/4-works.md)，直接输出**可执行的简洁框架**（非建议清单），控制在 1-2 页内

5. **保存**——`projects/<课程>/4-works/[原名]-4.md`

6. **后续**——完成课程后 → `/study-step5-final-summary`

---

## 命令：/study-run-full-flow

> 一次完整的学习循环 = 预 → 通 → 内 → 外

### 步骤

1. **确认**——课程名称、章节范围（可指定单章或多章）

2. **依次执行**——按顺序调用：
   - `/study-step1-preview`
   - `/study-step2-notes`
   - `/study-step3-anki-review`
   - `/study-step4-output-works`
   - 每阶段完成后确认是否继续
   - 用户可随时指定跳过某个阶段

3. **更新进度**——更新 `plan.md` 章节规划表状态（参见通用约定中的进度状态）

---

## 命令：/study-step5-final-summary

> 课程学习完毕后进行整体复盘和行动规划。

### 步骤

1. **确认结课状态**——扫描 `projects/` 确认课程，检查 `plan.md`，确认核心章节均已完成

2. **生成总结报告**——按模板 [templates/5-summary.md](templates/5-summary.md) 写入 `projects/<课程>/summary.md`：
   - **学习数据**：总耗时、笔记数量、卡片数量
   - **核心收获**：全书最重要的 3-5 个认知模型
   - **方法论/工具**：推荐工具和操作步骤
   - **资源速查**：书单、网站、App 清单
   - **行动计划**：短期（本周/本月）和长期（3-6 个月）

3. **更新 plan.md**——标记总结阶段完成，添加结课日志

**最佳实践**：不要罗列每章标题，要做跨章节的知识融合（Synthesis）。总结目的是"下一步做什么"，而非"我读了什么"。

---

## 脚本工具

```bash
# Anki 卡片生成（Markdown Q/A → TSV），输出至 3-review/anki-export/
python3 skills/learning-master/scripts/generate_anki_cards.py <review_file_or_dir>

# 指定自定义输出目录
python3 skills/learning-master/scripts/generate_anki_cards.py <review_dir> --output-dir <output_dir>
```

---

## 参考资料

- [templates/](templates/) — 各阶段笔记模板
