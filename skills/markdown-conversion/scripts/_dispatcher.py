"""Source-type detection and backend routing for markdown-conversion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


SUBTITLE_SUFFIXES = {".srt", ".vtt", ".ass"}
DOC_SUFFIXES = {
    ".docx", ".doc", ".odt", ".rtf",
    ".epub",
    ".html", ".htm",
    ".ipynb",
    ".tex", ".latex", ".rst", ".org", ".typ",
}
EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
LEGACY_EXCEL_SUFFIXES = {".xls"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
PDF_SUFFIXES = {".pdf"}
PPTX_SUFFIXES = {".pptx", ".pptm", ".ppsx", ".ppsm", ".potx", ".potm"}
TEXT_SUFFIXES = {".txt", ".text"}
SKIP_SUFFIXES = {".json", ".yaml", ".yml", ".log"}

BACKEND_SCRIPT_BY_TYPE = {
    "doc": "doc_to_md.py",
    "excel": "excel_to_md.py",
    "pdf": "pdf_to_md.py",
    "pptx": "ppt_to_md.py",
    "subtitle": "subtitle_to_md.py",
    "web": "web_to_md.py",
}


@dataclass(frozen=True)
class SourceRoute:
    """Resolved source route for one input."""

    conversion_type: str
    script_name: str | None


def is_url(value: str) -> bool:
    """Return whether value is an HTTP(S) URL."""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _url_path_suffix(value: str) -> str:
    return Path(urlparse(value).path).suffix.lower()


def detect_source_type(input_arg: str) -> str:
    """Detect a conversion type from a URL, file, or directory."""
    if is_url(input_arg):
        return "pdf" if _url_path_suffix(input_arg) in PDF_SUFFIXES else "web"

    path = Path(input_arg)
    if not path.exists():
        return "unknown"
    if path.is_dir():
        return "directory"

    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        return "pdf"
    if suffix in SUBTITLE_SUFFIXES:
        return "subtitle"
    if suffix in EXCEL_SUFFIXES or suffix in LEGACY_EXCEL_SUFFIXES:
        return "excel"
    if suffix in PPTX_SUFFIXES:
        return "pptx"
    if suffix in DOC_SUFFIXES:
        return "doc"
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    if suffix in TEXT_SUFFIXES:
        return "text"
    return "unknown"


def default_markdown_path(input_arg: str) -> Path:
    """Return the conventional Markdown output path for a local source."""
    path = Path(input_arg)
    return path.parent / f"{path.stem}.md"


def is_supported_directory_item(path: Path) -> bool:
    """Return whether a directory child should be expanded for conversion."""
    if path.name.startswith(".") or path.suffix.lower() in SKIP_SUFFIXES:
        return False
    return detect_source_type(str(path)) in {
        "pdf", "doc", "excel", "pptx", "subtitle", "markdown", "text",
    }


def resolve_route(input_arg: str, requested_type: str = "auto") -> SourceRoute:
    """Resolve one source to a normalized conversion type and backend script."""
    conversion_type = detect_source_type(input_arg) if requested_type == "auto" else requested_type
    if conversion_type == "sub":
        conversion_type = "subtitle"
    if conversion_type in {"markdown", "text", "directory", "unknown"}:
        return SourceRoute(conversion_type=conversion_type, script_name=None)
    return SourceRoute(
        conversion_type=conversion_type,
        script_name=BACKEND_SCRIPT_BY_TYPE.get(conversion_type),
    )
