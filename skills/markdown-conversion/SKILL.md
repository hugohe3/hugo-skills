---
name: markdown-conversion
description: >
  Convert source documents (PDF / Word / Excel / PowerPoint / EPUB / HTML / Jupyter /
  subtitles / web URL) into clean Markdown with images extracted alongside, ready for
  AI to read. Also batch-converts whole directories. Use when the user asks to turn
  a document into Markdown, "extract text from a PDF", "把文档转成 md", "网页转 markdown",
  "批量转 md", or prepares source material for downstream AI workflows.
---

# Markdown Conversion

Turn any supported source — a file, directory, or URL — into clean Markdown that an LLM can read. Each input becomes one `.md` (plus a sibling `<stem>_files/` folder for extracted images, when relevant).

## Quick start

The unified dispatcher auto-detects the input type:

```bash
python3 scripts/convert.py <file_or_url>
```

Default output: `<input_dir>/<stem>.md`.
Override file output with `-o <output.md>` for local file inputs; for directory inputs, `-o` is an output directory.
When the dispatcher knows the exact Markdown file path, it prints `OUTPUT: /abs/path/output.md` on success.

```bash
python3 scripts/convert.py paper.pdf                  # PDF (local PyMuPDF)
python3 scripts/convert.py paper.pdf --mineru         # PDF (MinerU cloud OCR)
python3 scripts/convert.py report.docx                # Word
python3 scripts/convert.py data.xlsx                  # Excel
python3 scripts/convert.py deck.pptx                  # PowerPoint
python3 scripts/convert.py book.epub                  # EPUB
python3 scripts/convert.py https://example.com/post   # Web page
python3 scripts/convert.py ./course_dir -t sub        # Subtitle batch
python3 scripts/convert.py ./mixed_docs               # Directory batch (any supported types)
```

## Batch directory conversion

`convert.py` accepts a directory and converts every supported file inside it (one level deep). Each file is dispatched to its own converter and written as `<stem>.md` next to the input (or under `-o`).

```bash
python3 scripts/convert.py ./mixed_docs               # convert each file in place
python3 scripts/convert.py ./mixed_docs -o ./out      # write all .md into ./out/
```

Batch mode continues after per-file failures and prints succeeded / failed / skipped counts.

For a very large PDF (book / long report), pre-split it with `pdftk`, `qpdf`, or PyPDF2 and feed the parts to `convert.py` — converters will also print a hint when a single PDF crosses ~200 pages.

## Supported sources

| Category | Extensions / inputs | Converter |
|---|---|---|
| PDF (text) | `.pdf` | `pdf_to_md.py` (PyMuPDF) |
| PDF (scanned, math-heavy, complex layout) | `.pdf` + `--mineru` | `pdf_to_md_mineru.py` |
| Word / EPUB / HTML / Jupyter | `.docx` `.epub` `.html` `.htm` `.ipynb` | `doc_to_md.py` (native) |
| Other office / academic | `.doc` `.odt` `.rtf` `.tex` `.rst` `.org` `.typ` | `doc_to_md.py` (pandoc fallback) |
| Spreadsheet | `.xlsx` `.xlsm` | `excel_to_md.py` |
| Slide deck | `.pptx` `.pptm` `.ppsx` `.ppsm` `.potx` `.potm` | `ppt_to_md.py` |
| Subtitles | `.srt` `.vtt` `.ass` (single file, flat directory, or course directory) | `subtitle_to_md.py` |
| Web page | `http://` / `https://` | `web_to_md.py` (Python, curl_cffi) |
| Plain text | `.txt` | passthrough |
| Already Markdown | `.md` `.markdown` | passthrough |

`.xls` and legacy `.ppt` are not parsed directly — resave as `.xlsx` / `.pptx` first. `.doc` works through the pandoc fallback.

## Calling a converter directly

`convert.py` is the recommended entry point, but every backend is also a standalone CLI:

```bash
python3 scripts/pdf_to_md.py book.pdf
python3 scripts/pdf_to_md_mineru.py scan.pdf            # needs MINERU_API_TOKEN
python3 scripts/doc_to_md.py paper.tex                  # uses pandoc
python3 scripts/excel_to_md.py report.xlsm --max-rows 200 --max-cols 40
python3 scripts/ppt_to_md.py deck.pptx
python3 scripts/web_to_md.py https://mp.weixin.qq.com/s/xxxx
python3 scripts/subtitle_to_md.py lecture.srt
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

MinerU needs `MINERU_API_TOKEN` or a local, gitignored `resources/config.json` copied from `resources/config.example.json`.

## Web fetching

`web_to_md.py` covers all URLs. With `curl_cffi` installed it impersonates Chrome's TLS fingerprint and can fetch WeChat Official Accounts (`mp.weixin.qq.com`) and other sites that block Python's default fingerprint — no flag needed. Without `curl_cffi`, it falls back to plain `requests` (sufficient for most public sites).

## Diagnostics

```bash
python3 scripts/check_env.py    # per-format readiness table: Python deps, pandoc, MinerU token
```

## Setup

```bash
pip install -r resources/requirements.txt
python3 scripts/check_env.py
```

`check_env.py` prints a per-format readiness table — green entries are usable now; missing-dependency entries point to the package or binary needed.

`pandoc` is optional — only needed for the long-tail document formats (`.doc` / `.odt` / `.rtf` / `.tex` / `.rst` / `.org` / `.typ`).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pandoc not found` while converting `.doc`/`.tex`/etc. | `brew install pandoc` (macOS) or `sudo apt install pandoc` |
| `MinerU` calls fail with auth error | Set `MINERU_API_TOKEN`, or copy `resources/config.example.json` to the gitignored `resources/config.json` and fill the token |
| WeChat / Cloudflare URLs return 403 | Install `curl_cffi` so `web_to_md.py` can impersonate a real Chrome TLS fingerprint |
| Auto-detect picks the wrong type | Force it with `-t pdf\|doc\|excel\|pptx\|web\|sub` |
| File extension is unusual (e.g. `.pdf.bak`) | Use `-t` to force the type |

## Output convention

- Input file → `<input_dir>/<stem>.md` (unless `-o` is given)
- Embedded images → `<input_dir>/<stem>_files/` with relative references in the Markdown
- URL → current working directory unless `-o` is given; PDF URLs routed through MinerU use MinerU's output directory behavior
- Already-Markdown / plain-text inputs are echoed (or copied) without conversion
