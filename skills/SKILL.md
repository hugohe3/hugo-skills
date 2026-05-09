---
name: markdown-conversion
description: >
  Convert source documents (PDF / Word / Excel / PowerPoint / EPUB / HTML / Jupyter /
  subtitles / web URL) into clean Markdown with images extracted alongside. Use when
  the user asks to turn a document into Markdown, "extract text from a PDF", "把文档转成 md",
  "网页转 markdown", or prepares source material for downstream AI workflows.
---

# Markdown Conversion

Takes one input — file, directory, or URL — and writes a single `.md` next to it (plus a sibling `<stem>_files/` folder for extracted images, when relevant).

## Quick start

The unified dispatcher auto-detects the input type:

```bash
python scripts/convert.py <file_or_url>
```

Default output: `<input_dir>/<stem>.md`.
Override: `-o <output.md>`.
On success, the last stdout line is `OUTPUT: /abs/path/output.md` — use it to locate the result programmatically.

```bash
python scripts/convert.py paper.pdf                  # PDF (local PyMuPDF)
python scripts/convert.py paper.pdf --mineru         # PDF (MinerU cloud OCR)
python scripts/convert.py report.docx                # Word
python scripts/convert.py data.xlsx                  # Excel
python scripts/convert.py deck.pptx                  # PowerPoint
python scripts/convert.py book.epub                  # EPUB
python scripts/convert.py https://example.com/post   # Web page
python scripts/convert.py ./course_dir -t sub        # Subtitle batch
```

## Supported sources

| Category | Extensions / inputs | Converter |
|---|---|---|
| PDF (text) | `.pdf` | `pdf_to_md.py` (PyMuPDF) |
| PDF (scanned, math-heavy, complex layout) | `.pdf` + `--mineru` | `pdf_to_md_mineru.py` |
| Word / EPUB / HTML / Jupyter | `.docx` `.epub` `.html` `.htm` `.ipynb` | `doc_to_md.py` (native) |
| Other office / academic | `.doc` `.odt` `.rtf` `.tex` `.rst` `.org` `.typ` | `doc_to_md.py` (pandoc fallback) |
| Spreadsheet | `.xlsx` `.xlsm` | `excel_to_md.py` |
| Slide deck | `.pptx` `.pptm` `.ppsx` `.ppsm` `.potx` `.potm` | `ppt_to_md.py` |
| Subtitles | `.srt` `.vtt` `.ass` (file or directory) | `subtitle_to_md.py` |
| Web page | `http://` / `https://` | `web_to_md.py` (Python, curl_cffi) |
| Plain text | `.txt` | passthrough |
| Already Markdown | `.md` `.markdown` | passthrough |

`.xls` and legacy `.ppt` are not parsed directly — resave as `.xlsx` / `.pptx` first. `.doc` works through the pandoc fallback.

## Calling a converter directly

`convert.py` is the recommended entry point, but every backend is also a standalone CLI:

```bash
python scripts/pdf_to_md.py book.pdf
python scripts/pdf_to_md_mineru.py scan.pdf            # needs MINERU_API_TOKEN
python scripts/doc_to_md.py paper.tex                  # uses pandoc
python scripts/excel_to_md.py report.xlsm --max-rows 200 --max-cols 40
python scripts/ppt_to_md.py deck.pptx
python scripts/web_to_md.py https://mp.weixin.qq.com/s/xxxx
python scripts/subtitle_to_md.py lecture.srt
```

Each script writes `<input>.md` plus `<input>_files/` for embedded images, with relative references in the Markdown.

## Choosing between PDF backends

Always start with the local parser. Switch only after inspecting the output.

| Situation | Action |
|---|---|
| Output is readable | Done — keep the local result |
| Garbled text, broken reading order, missing content | Re-run with `--mineru` |
| Scanned PDF, image-only PDF | Use `--mineru` directly |
| PDF from a URL | `convert.py` routes to MinerU automatically |

MinerU needs an API token in `resources/config.json` (`{"mineru_api_token": "..."}`) or the env var `MINERU_API_TOKEN`.

## Web fetching

`web_to_md.py` covers all URLs. With `curl_cffi` installed it impersonates Chrome's TLS fingerprint and can fetch WeChat Official Accounts (`mp.weixin.qq.com`) and other sites that block Python's default fingerprint — no flag needed. Without `curl_cffi`, it falls back to plain `requests` (sufficient for most public sites).

## Utilities

| Script | Purpose |
|---|---|
| `split_pdf.py <file.pdf>` | Split a PDF by detected chapters |
| `split_md.py <file.md>` | Split a long Markdown file by headings |
| `merge_md.py <dir/>` | Merge Markdown files in a directory |
| `check_env.py` | Verify Python packages, pandoc, MinerU token |

## Setup

```bash
pip install -r resources/requirements.txt
python scripts/check_env.py
```

`check_env.py` prints a per-format readiness table — green entries are usable now; missing-dependency entries point to the package or binary needed.

`pandoc` is optional — only needed for the long-tail document formats (`.doc` / `.odt` / `.rtf` / `.tex` / `.rst` / `.org` / `.typ`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pandoc not found` while converting `.doc`/`.tex`/etc. | `brew install pandoc` (macOS) or `sudo apt install pandoc` |
| `MinerU` calls fail with auth error | Set `MINERU_API_TOKEN` env var or add it to `resources/config.json` |
| WeChat / Cloudflare URLs return 403 | Install `curl_cffi` so `web_to_md.py` can impersonate a real Chrome TLS fingerprint |
| Auto-detect picks the wrong type | Force it with `-t pdf\|doc\|excel\|pptx\|web\|sub` |
| File extension is unusual (e.g. `.pdf.bak`) | Use `-t` to force the type |

## Output convention

- Input file → `<input_dir>/<stem>.md` (unless `-o` is given)
- Embedded images → `<input_dir>/<stem>_files/` with relative references in the Markdown
- URL → current working directory unless `-o` is given
- Already-Markdown / plain-text inputs are echoed (or copied) without conversion
