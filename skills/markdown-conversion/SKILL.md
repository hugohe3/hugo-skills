---
name: markdown-conversion
description: >
  Convert source documents (PDF / Word / Excel / PowerPoint / EPUB / HTML / Jupyter /
  subtitles / web URL) into clean Markdown with images extracted alongside, ready for
  AI to read. Also batch-converts whole directories. Use when the user asks to turn
  a document into Markdown, "extract text from a PDF", "把文档转成 md", "网页转 markdown",
  "批量转 md", or prepares source material for downstream AI workflows.
---

# Markdown 转换

将任意支持的来源——文件、目录或 URL——转换为 LLM 可读的干净 Markdown。每个输入生成一个 `.md` 文件（以及提取图片时相应的 `<stem>_files/` 文件夹）。

## 快速开始

统一调度器会自动识别输入类型：

```bash
python3 scripts/convert.py <文件或URL>
```

默认输出：`<输入目录>/<文件名>.md`。
本地文件可用 `-o <output.md>` 指定输出路径；目录输入时，`-o` 为输出目录。
调度器成功后会打印 `OUTPUT: /绝对路径/output.md`。

```bash
python3 scripts/convert.py paper.pdf                  # PDF（本地 PyMuPDF）
python3 scripts/convert.py paper.pdf --mineru         # PDF（MinerU 云端 OCR）
python3 scripts/convert.py report.docx                # Word
python3 scripts/convert.py data.xlsx                  # Excel
python3 scripts/convert.py deck.pptx                  # PowerPoint
python3 scripts/convert.py book.epub                  # EPUB
python3 scripts/convert.py https://example.com/post   # 网页
python3 scripts/convert.py ./course_dir -t sub        # 字幕批量
python3 scripts/convert.py ./mixed_docs               # 目录批量（所有支持类型）
```

## 批量目录转换

`convert.py` 接受目录参数，转换其中所有支持的文件（一层深度）。每个文件由对应转换器处理，输出为 `<文件名>.md`（或写入 `-o` 指定目录）。

```bash
python3 scripts/convert.py ./mixed_docs               # 原位转换每个文件
python3 scripts/convert.py ./mixed_docs -o ./out      # 所有 .md 写入 ./out/
```

批量模式在单文件失败后继续运行，最后打印成功 / 失败 / 跳过计数。

超大 PDF（书籍/长报告）可先用 `pdftk`、`qpdf` 或 PyPDF2 拆分再转换——单个 PDF 超过约 200 页时转换器也会提示。

## 支持的来源

| 类型 | 扩展名 / 输入 | 转换器 |
|---|---|---|
| PDF（文本型） | `.pdf` | `pdf_to_md.py`（PyMuPDF） |
| PDF（扫描件、公式密集、复杂排版） | `.pdf` + `--mineru` | `pdf_to_md_mineru.py` |
| Word / EPUB / HTML / Jupyter | `.docx` `.epub` `.html` `.htm` `.ipynb` | `doc_to_md.py`（原生） |
| 其他办公 / 学术格式 | `.doc` `.odt` `.rtf` `.tex` `.rst` `.org` `.typ` | `doc_to_md.py`（pandoc 回退） |
| 电子表格 | `.xlsx` `.xlsm` | `excel_to_md.py` |
| 幻灯片 | `.pptx` `.pptm` `.ppsx` `.ppsm` `.potx` `.potm` | `ppt_to_md.py` |
| 字幕 | `.srt` `.vtt` `.ass`（单文件、平级目录或课程目录） | `subtitle_to_md.py` |
| 网页 | `http://` / `https://` | `web_to_md.py`（Python，curl_cffi） |
| 纯文本 | `.txt` | 直通 |
| 已是 Markdown | `.md` `.markdown` | 直通 |

`.xls` 和旧版 `.ppt` 不直接解析——请先另存为 `.xlsx` / `.pptx`。`.doc` 通过 pandoc 回退处理。

## 直接调用转换器

`convert.py` 是推荐入口，但每个后端也可作为独立 CLI 使用：

```bash
python3 scripts/pdf_to_md.py book.pdf
python3 scripts/pdf_to_md_mineru.py scan.pdf            # 需要 MINERU_API_TOKEN
python3 scripts/doc_to_md.py paper.tex                  # 使用 pandoc
python3 scripts/excel_to_md.py report.xlsm --max-rows 200 --max-cols 40
python3 scripts/ppt_to_md.py deck.pptx
python3 scripts/web_to_md.py https://mp.weixin.qq.com/s/xxxx
python3 scripts/subtitle_to_md.py lecture.srt
```

每个脚本输出 `<输入>.md` 及嵌入图片的 `<输入>_files/`，Markdown 中使用相对路径引用。

## 选择 PDF 后端

始终先用本地解析器，检查输出后再决定是否切换。

| 情况 | 操作 |
|---|---|
| 输出可读 | 完成——保留本地结果 |
| 乱码、阅读顺序混乱、内容缺失 | 改用 `--mineru` 重新运行 |
| 扫描件、纯图片 PDF | 直接使用 `--mineru` |
| 来自 URL 的 PDF | `convert.py` 自动路由到 MinerU |

MinerU 需要 `MINERU_API_TOKEN`，或将 `resources/config.example.json` 复制为 gitignore 的 `resources/config.json` 并填入 token。

## 网页抓取

`web_to_md.py` 支持所有 URL。安装 `curl_cffi` 后可模拟 Chrome TLS 指纹，能抓取微信公众号（`mp.weixin.qq.com`）等屏蔽 Python 默认指纹的站点——无需额外参数。未安装时回退到标准 `requests`（大多数公开网站够用）。

## 环境诊断

```bash
python3 scripts/check_env.py    # 按格式显示就绪状态：Python 依赖、pandoc、MinerU token
```

## 安装

```bash
pip install -r resources/requirements.txt
python3 scripts/check_env.py
```

`check_env.py` 打印按格式分类的就绪表——绿色表示可用，缺依赖项会指出所需包或二进制。

`pandoc` 可选——仅处理长尾文档格式（`.doc` / `.odt` / `.rtf` / `.tex` / `.rst` / `.org` / `.typ`）时需要。

## 故障排查

| 症状 | 解决方法 |
|---|---|
| 转换 `.doc`/`.tex` 等时提示 `pandoc not found` | `brew install pandoc`（macOS）或 `sudo apt install pandoc` |
| `MinerU` 调用报认证错误 | 设置 `MINERU_API_TOKEN`，或将 `resources/config.example.json` 复制为 gitignore 的 `resources/config.json` 并填入 token |
| 微信 / Cloudflare URL 返回 403 | 安装 `curl_cffi` 让 `web_to_md.py` 模拟真实 Chrome TLS 指纹 |
| 自动识别类型错误 | 用 `-t pdf\|doc\|excel\|pptx\|web\|sub` 强制指定 |
| 文件扩展名异常（如 `.pdf.bak`） | 用 `-t` 强制指定类型 |

## 输出约定

- 输入文件 → `<输入目录>/<文件名>.md`（除非指定 `-o`）
- 嵌入图片 → `<输入目录>/<文件名>_files/`，Markdown 中使用相对路径引用
- URL → 当前工作目录（除非指定 `-o`）；经 MinerU 处理的 PDF URL 使用 MinerU 的输出目录行为
- 已是 Markdown / 纯文本的输入直接输出（或复制）不做转换
