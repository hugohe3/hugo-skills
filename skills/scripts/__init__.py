"""Markdown Conversion toolkit

Python utilities for converting source documents to Markdown:

Entry point:
- convert: Auto-detect input type and dispatch to the right converter

PDF:
- pdf_to_md: PyMuPDF local PDF to Markdown (default — fast, offline)
- pdf_to_md_mineru: MinerU cloud OCR (scanned PDFs, math-heavy or complex layouts)
- split_pdf: PDF splitter (bookmark / chapter / section modes)

Document conversion:
- doc_to_md: Word / EPUB / HTML / Jupyter native + pandoc fallback for .doc / .tex / etc.
- excel_to_md: .xlsx / .xlsm to Markdown tables
- ppt_to_md: PowerPoint (.pptx and friends) to Markdown
- subtitle_to_md: .srt / .vtt / .ass to Markdown
- web_to_md: Web page to Markdown with curl_cffi TLS impersonation

Markdown processing:
- merge_md: Merge multiple Markdown files into one
- split_md: Split a Markdown file by headings
"""

from pathlib import Path

# Tools directory
TOOLS_DIR = Path(__file__).parent

# Version
__version__ = "1.0.0"
