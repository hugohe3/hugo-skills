---
name: epub-translator
description: >
  Translate English EPUB books into Simplified Chinese EPUB files with the current
  agent's model, without requiring any model API key or vendor-specific SDK. Preserve
  the original EPUB structure, images, CSS, metadata, links, and reading order. Use
  when the user asks to translate an .epub book, "英文 epub 翻译成中文 epub",
  "translate epub to Chinese", or produce a Chinese EPUB from an English EPUB.
---

# EPUB 翻译

将英文 `.epub` 书籍翻译为简体中文 `.epub`。模型调用由当前聊天环境中的主代理或子代理完成；本技能不绑定 OpenAI、Claude、Gemini 或任何特定 API。

脚本只做确定性的 EPUB 工程处理：

```text
解包 EPUB → 提取正文/目录/元数据文本分块 → agent 翻译 JSONL → 写回 EPUB → 重新打包 EPUB
```

## 快速开始

先把 EPUB 拆成待翻译分块：

```bash
python3 scripts/translate_epub.py prepare book.epub -w work/book-zh
```

翻译 `work/book-zh/chunks/*.jsonl`，把译文写入 `work/book-zh/translated/` 下同名 JSONL 文件。

检查是否全部翻译完成：

```bash
python3 scripts/translate_epub.py check -w work/book-zh
```

生成中文 EPUB：

```bash
python3 scripts/translate_epub.py build -w work/book-zh -o book.zh-Hans.epub
```

## 翻译分块格式

`prepare` 会从正文 XHTML、EPUB 3 `nav.xhtml`、EPUB 2 `toc.ncx` 和 OPF 标题元数据中生成 JSONL 文件，每行一个文本节点：

```json
{"id":"t000001","source":"Chapter 1","translation":""}
```

翻译时必须：

- 保留每行 JSONL 一行一条记录。
- 保留 `id` 和 `source`。
- 只填写 `translation` 字段。
- 不新增解释、摘要、注释或额外字段。
- 不合并、拆分、重排记录。
- 如果 `source` 中包含 `[t:0]`、`[t:1]` 这类标签占位符，`translation` 中必须按原数量和原顺序保留；这些占位符代表链接、脚注、斜体、粗体等 EPUB 内联标签。

翻译后示例：

```json
{"id":"t000001","source":"Chapter 1","translation":"第一章"}
```

## agent 工作流

1. 确认输入是 `.epub` 文件，并确定输出路径；默认建议 `<原文件名>.zh-Hans.epub`。
2. 运行 `prepare`，生成 `manifest.json`、`chunks/`、`translated/` 和解包后的 `source/`；提取范围包含正文、目录和书名 metadata。
3. **建立术语表**：在翻译前，先通读/扫描所有待翻译的文本内容，识别出书中的高频核心专业词汇、专有名词、主要人物姓名或特定短语，在工作目录下建立统一的术语对照表（如 `glossary.md`），确保后续翻译中术语的前后一致性。
4. 按 chunk 翻译：
   - 小书可由主代理逐个处理 `chunks/*.jsonl`。
   - 大书可并行分配给子代理，每个子代理只处理若干 chunk。
   - 每个子代理翻译前必须读取 `glossary.md`，并按其中译名保持术语一致。
   - 子代理产物必须写入 `translated/chunk-xxxx.jsonl`，不要改动 `source/`。
5. 运行 `check`，确保所有 `id` 都有非空 `translation`，且不存在重复 ID、未知 ID、空白译文或占位符不匹配。
6. 运行 `build`，把译文写回正文、目录和 metadata，并把 EPUB 语言代码更新为 `zh-Hans` 后重打包。
7. 抽查输出 EPUB：目录页、前言、第一章、含脚注章节、含图片章节。

## 翻译原则

- 目标语言：默认简体中文。
- 保留原意、语气、段落边界和阅读节奏。
- 人名、品牌名、专有名词可保留英文；必要时使用自然中文译名。
- 术语前后一致；同一 chunk 内不要反复改译。
- 不翻译 URL、邮箱、代码、命令、文件名、锚点。
- 不删减内容；不因为文本重复、枯燥或短小而跳过。
- 不添加原书没有的解释、总结、标题或译者注。

## CLI 命令

| 命令 | 说明 |
|---|---|
| `prepare <book.epub> -w <work-dir>` | 解包 EPUB，提取待翻译 JSONL 分块 |
| `check -w <work-dir>` | 检查 `translated/` 中译文是否完整 |
| `build -w <work-dir> -o <output.epub>` | 写回译文并重新打包 EPUB |

常用选项：

| 选项 | 说明 |
|---|---|
| `--source-language` | 源语言标签，默认 `English` |
| `--target-language` | 目标语言标签，默认 `Simplified Chinese` |
| `--target-language-code` | 写入 EPUB metadata 的目标语言代码，默认 `zh-Hans` |
| `--chunk-chars` | 每个 chunk 的近似源文本字符数，默认 `8000` |
| `--force` | `prepare` 时覆盖已有工作目录 |
| `--allow-missing` | `build` 时允许缺失译文并保留原文 |

## 失败处理

| 症状 | 处理 |
|---|---|
| `work directory already exists` | 换一个工作目录；确认可覆盖时再用 `--force` |
| `MISSING` 大于 0 | 补齐 `translated/*.jsonl` 中缺失或空的 `translation` |
| `duplicate id` | 删除重复记录，只保留该 `id` 的一条译文 |
| `unknown id` | 删除不在 `manifest.json` 中的多余记录 |
| `blank translation` | 补齐对应 `translation`，不要只写空格 |
| 输出 EPUB 打不开 | 确认输入 EPUB 本身可打开；重新运行 `build` |
| 局部章节仍是英文 | 运行 `check`，并搜索 `translated/` 中空译文字段 |
| 阅读器目录仍是英文 | 确认 EPUB 的 `nav.xhtml` 或 `toc.ncx` 已出现在 `manifest.json` 的 `documents` 中，并检查对应 chunk 是否已翻译 |
| 构建时报占位符不匹配 | 重新翻译对应记录，确保 `[t:n]` 占位符数量和顺序与 `source` 完全一致 |
| 子代理输出破坏 JSONL | 让子代理只重写对应 chunk，并保持一行一个 JSON 对象 |

## 安装

脚本只使用 Python 标准库，无需安装第三方依赖。
