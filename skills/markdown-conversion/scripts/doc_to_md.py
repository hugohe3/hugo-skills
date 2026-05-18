#!/usr/bin/env python3
"""
Document to Markdown Converter (hybrid Python + Pandoc fallback)

Primary formats (pure Python, no external tools required):
    .docx   → mammoth
    .html   → markdownify + BeautifulSoup
    .epub   → ebooklib + markdownify
    .ipynb  → nbconvert

Fallback formats (require pandoc installed):
    .doc .odt .rtf .tex .latex .rst .org .typ

All paths produce the same output convention:
    <input>.md                     Markdown file
    <input>_files/<asset>          Extracted media (relative references in MD)
"""

import argparse
import base64
import mimetypes
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).parent))
from _image_filter import should_keep_image_bytes  # noqa: E402

# ─────────────────────────────────────────────────────────────
# Format registry
# ─────────────────────────────────────────────────────────────

# Formats handled by pure-Python paths
NATIVE_FORMATS = {".docx", ".html", ".htm", ".epub", ".ipynb"}

# Formats handled by pandoc fallback: suffix → (pandoc input format, description)
PANDOC_FORMATS = {
    ".doc":   ("doc",    "Microsoft Word 97-2003"),
    ".odt":   ("odt",    "OpenDocument Text"),
    ".rtf":   ("rtf",    "Rich Text Format"),
    ".tex":   ("latex",  "LaTeX"),
    ".latex": ("latex",  "LaTeX"),
    ".rst":   ("rst",    "reStructuredText"),
    ".org":   ("org",    "Emacs Org-mode"),
    ".typ":   ("typst",  "Typst"),
}

# Formats pandoc should extract embedded media from
PANDOC_MEDIA_FORMATS = {".odt"}


# ─────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────

def _format_size(size: int) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _ensure_media_dir(out_file: Path) -> tuple[Path, str]:
    """Return (absolute media dir, relative dir name) and create the dir."""
    rel_media_dir = f"{out_file.stem}_files"
    media_dir = out_file.parent / rel_media_dir
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir, rel_media_dir


_HTML_IMG_PATTERNS = (
    re.compile(
        r'<img\s[^>]*?src="(?P<src>[^"]+)"[^>]*?(?:alt="(?P<alt>[^"]*)")?[^>]*/?\s*>'
    ),
    re.compile(
        r'<img\s[^>]*?alt="(?P<alt>[^"]*)"[^>]*?src="(?P<src>[^"]+)"[^>]*/?\s*>'
    ),
)


def _html_img_to_md(markdown_content: str) -> str:
    """Convert any leftover <img> HTML tags to ![alt](src) syntax."""
    def _repl(match: re.Match[str]) -> str:
        src = match.group("src")
        alt = match.group("alt") or Path(src).stem
        return f"![{alt}]({src})"

    for pattern in _HTML_IMG_PATTERNS:
        markdown_content = pattern.sub(_repl, markdown_content)
    return markdown_content


_MD_IMAGE_REF_RE = re.compile(r'!\[[^\]]*\]\([^)]*\)')


def _strip_image_refs(markdown: str) -> str:
    """Drop all ![alt](src) image references; remove image-only lines."""
    out: list[str] = []
    for line in markdown.splitlines():
        stripped = _MD_IMAGE_REF_RE.sub("", line)
        if line.strip() and not stripped.strip():
            continue
        out.append(stripped)
    return re.sub(r'\n{3,}', '\n\n', "\n".join(out))


def _report_result(out_file: Path, media_dir: Path | None) -> None:
    size = out_file.stat().st_size
    print(f"[OK] Saved Markdown to: {out_file} ({_format_size(size)})")
    if media_dir and media_dir.exists():
        files = [f for f in media_dir.rglob("*") if f.is_file()]
        if files:
            print(f"   Extracted {len(files)} media file(s) → {media_dir}")


# ─────────────────────────────────────────────────────────────
# DOCX → Markdown (mammoth)
# ─────────────────────────────────────────────────────────────

def _convert_docx(input_file: Path, out_file: Path, no_images: bool = False, filter_images: bool = False) -> str:
    try:
        import mammoth
    except ImportError:
        print("[ERROR] mammoth not installed. Run: pip install mammoth")
        return ""

    media_dir: Path | None
    if no_images:
        media_dir = None
        rel_media_dir = ""

        def _save_image(image):
            return {"src": ""}
    else:
        media_dir, rel_media_dir = _ensure_media_dir(out_file)
        counter = {"n": 0}
        seen_hashes: set[str] = set()

        def _save_image(image):
            with image.open() as stream:
                payload = stream.read()
            if filter_images and not should_keep_image_bytes(payload, seen_hashes=seen_hashes):
                # Decorative / duplicate — leave reference empty so post-strip drops it.
                return {"src": ""}
            counter["n"] += 1
            ext = mimetypes.guess_extension(image.content_type) or ".bin"
            if ext == ".jpe":
                ext = ".jpg"
            filename = f"image_{counter['n']:03d}{ext}"
            (media_dir / filename).write_bytes(payload)
            return {"src": f"{rel_media_dir}/{filename}"}

    with input_file.open("rb") as f:
        result = mammoth.convert_to_markdown(
            f,
            convert_image=mammoth.images.img_element(_save_image),
        )

    markdown = _html_img_to_md(result.value)
    if no_images or filter_images:
        # `no_images` drops everything; `filter_images` drops the filtered-out empties.
        markdown = _strip_image_refs(markdown) if no_images else re.sub(
            r'!\[[^\]]*\]\(\)\s*\n?', '', markdown
        )
    out_file.write_text(markdown, encoding="utf-8")

    if media_dir is not None and not any(media_dir.iterdir()):
        media_dir.rmdir()
        media_dir = None

    for msg in result.messages:
        if msg.type == "warning":
            print(f"   [warn] {msg.message}")

    _report_result(out_file, media_dir)
    return markdown


# ─────────────────────────────────────────────────────────────
# HTML → Markdown (markdownify + BeautifulSoup)
# ─────────────────────────────────────────────────────────────

def _save_data_uri(data_uri: str, media_dir: Path, index: int, filter_images: bool, seen_hashes: set[str]) -> str | None:
    """Decode data:image/...;base64,... into a file; return filename or None."""
    match = re.match(r"data:(?P<mime>[^;]+);base64,(?P<data>.+)", data_uri)
    if not match:
        return None
    mime = match.group("mime")
    ext = mimetypes.guess_extension(mime) or ".bin"
    if ext == ".jpe":
        ext = ".jpg"
    try:
        payload = base64.b64decode(match.group("data"))
    except Exception:
        return None
    if filter_images and not should_keep_image_bytes(payload, seen_hashes=seen_hashes):
        return None
    filename = f"image_{index:03d}{ext}"
    try:
        (media_dir / filename).write_bytes(payload)
    except Exception:
        return None
    return filename


def _copy_local_image(src: str, base_dir: Path, media_dir: Path, index: int, filter_images: bool, seen_hashes: set[str]) -> str | None:
    """Copy a local image (relative or file://) into media_dir."""
    parsed = urlparse(src)
    if parsed.scheme in ("http", "https"):
        return None
    path_str = unquote(parsed.path if parsed.scheme == "file" else src)
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    if not candidate.is_file():
        return None
    if filter_images:
        try:
            payload = candidate.read_bytes()
        except Exception:
            return None
        if not should_keep_image_bytes(payload, seen_hashes=seen_hashes):
            return None
    ext = candidate.suffix or ".bin"
    filename = f"image_{index:03d}{ext}"
    shutil.copy2(candidate, media_dir / filename)
    return filename


def _download_remote_image(url: str, media_dir: Path, index: int, filter_images: bool, seen_hashes: set[str]) -> str | None:
    """Best-effort download of a remote image. Silent on failure."""
    try:
        import requests
    except ImportError:
        return None
    try:
        resp = requests.get(url, timeout=10, stream=True)
        resp.raise_for_status()
    except Exception:
        return None
    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
    if filter_images and not should_keep_image_bytes(resp.content, seen_hashes=seen_hashes):
        return None
    ext = mimetypes.guess_extension(content_type) if content_type else None
    if not ext:
        ext = Path(urlparse(url).path).suffix or ".bin"
    if ext == ".jpe":
        ext = ".jpg"
    filename = f"image_{index:03d}{ext}"
    (media_dir / filename).write_bytes(resp.content)
    return filename


def _process_html_images(html: str, base_dir: Path, media_dir: Path, rel_media_dir: str, filter_images: bool = False) -> str:
    """Extract & rewrite all <img> srcs in an HTML string."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[ERROR] beautifulsoup4 not installed. Run: pip install beautifulsoup4")
        return html

    soup = BeautifulSoup(html, "html.parser")
    index = 0
    seen_hashes: set[str] = set()
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if not src:
            continue
        index += 1
        if src.startswith("data:"):
            filename = _save_data_uri(src, media_dir, index, filter_images, seen_hashes)
        elif urlparse(src).scheme in ("http", "https"):
            filename = _download_remote_image(src, media_dir, index, filter_images, seen_hashes)
        else:
            filename = _copy_local_image(src, base_dir, media_dir, index, filter_images, seen_hashes)
        if filename:
            img["src"] = f"{rel_media_dir}/{filename}"
        elif filter_images:
            # Filtered out — drop the <img> so no broken reference leaks.
            img.decompose()
    return str(soup)


def _convert_html(input_file: Path, out_file: Path, no_images: bool = False, filter_images: bool = False) -> str:
    try:
        from markdownify import markdownify
    except ImportError:
        print("[ERROR] markdownify not installed. Run: pip install markdownify")
        return ""

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[ERROR] beautifulsoup4 not installed. Run: pip install beautifulsoup4")
        return ""

    media_dir: Path | None
    if no_images:
        media_dir = None
    else:
        media_dir, rel_media_dir = _ensure_media_dir(out_file)
    raw_html = input_file.read_text(encoding="utf-8", errors="replace")

    # Strip non-content elements (head/style/script) so metadata doesn't leak into MD
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["head", "style", "script", "noscript"]):
        tag.decompose()
    if no_images:
        for img in soup.find_all("img"):
            img.decompose()
        html = str(soup)
    else:
        html = str(soup)
        html = _process_html_images(html, input_file.parent, media_dir, rel_media_dir, filter_images=filter_images)

    markdown = markdownify(html, heading_style="ATX", bullets="-")
    # Collapse 3+ blank lines to 2 for tidier output
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip() + "\n"
    out_file.write_text(markdown, encoding="utf-8")

    if media_dir is not None and not any(media_dir.iterdir()):
        media_dir.rmdir()
        media_dir = None

    _report_result(out_file, media_dir)
    return markdown


# ─────────────────────────────────────────────────────────────
# EPUB → Markdown (ebooklib + markdownify)
# ─────────────────────────────────────────────────────────────

def _convert_epub(input_file: Path, out_file: Path, no_images: bool = False, filter_images: bool = False) -> str:
    try:
        import ebooklib
        from ebooklib import epub
        from markdownify import markdownify
        from bs4 import BeautifulSoup
    except ImportError as e:
        print(f"[ERROR] Missing dependency: {e.name}. "
              f"Run: pip install ebooklib markdownify beautifulsoup4")
        return ""

    media_dir: Path | None
    img_map: dict[str, str] = {}
    if no_images:
        media_dir = None
        rel_media_dir = ""
    else:
        media_dir, rel_media_dir = _ensure_media_dir(out_file)
    book = epub.read_epub(str(input_file))

    # Extract images, remembering original path → new filename mapping
    if not no_images:
        index = 0
        seen_hashes: set[str] = set()
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            payload = item.get_content()
            if filter_images and not should_keep_image_bytes(payload, seen_hashes=seen_hashes):
                continue
            index += 1
            ext = Path(item.file_name).suffix or ".bin"
            filename = f"image_{index:03d}{ext}"
            (media_dir / filename).write_bytes(payload)
            # Map both full and basename for robust lookup
            img_map[item.file_name] = filename
            img_map[Path(item.file_name).name] = filename

    # Iterate document items in spine order
    html_parts: list[str] = []
    spine_ids = [sid for sid, _ in book.spine]
    id_to_item = {it.get_id(): it for it in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)}
    for sid in spine_ids:
        item = id_to_item.get(sid)
        if item is None:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        if no_images:
            for img in soup.find_all("img"):
                img.decompose()
        else:
            for img in soup.find_all("img"):
                src = img.get("src", "")
                if not src:
                    continue
                # Try exact match, then basename, then normalized path
                candidates = [src, Path(src).name, unquote(src), Path(unquote(src)).name]
                resolved = next((img_map[c] for c in candidates if c in img_map), None)
                if resolved:
                    img["src"] = f"{rel_media_dir}/{resolved}"
                elif filter_images:
                    # The image was filtered out by filter_images — drop the reference.
                    img.decompose()
        body = soup.find("body") or soup
        html_parts.append(str(body))

    combined_html = "\n\n".join(html_parts)
    markdown = markdownify(combined_html, heading_style="ATX", bullets="-")
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip() + "\n"
    out_file.write_text(markdown, encoding="utf-8")

    if media_dir is not None and not any(media_dir.iterdir()):
        media_dir.rmdir()
        media_dir = None

    _report_result(out_file, media_dir)
    return markdown


# ─────────────────────────────────────────────────────────────
# IPYNB → Markdown (nbconvert)
# ─────────────────────────────────────────────────────────────

def _convert_ipynb(input_file: Path, out_file: Path, no_images: bool = False, filter_images: bool = False) -> str:
    try:
        import nbformat
        from nbconvert import MarkdownExporter
        from nbconvert.writers import FilesWriter
    except ImportError:
        print("[ERROR] nbconvert not installed. Run: pip install nbconvert")
        return ""

    # Pre-process cell-level markdown attachments: nbconvert leaves
    # `attachment:<name>` references intact but doesn't write the files.
    # Extract them into our outputs dict so FilesWriter picks them up.
    nb = nbformat.read(str(input_file), as_version=4)
    extra_outputs: dict[str, bytes] = {}
    rel_media_dir = f"{out_file.stem}_files"

    attach_counter = 0
    for cell in nb.cells:
        if cell.cell_type != "markdown":
            continue
        attachments = getattr(cell, "attachments", None) or {}
        if not attachments:
            continue
        for att_name, mime_data in attachments.items():
            for mime, b64 in mime_data.items():
                attach_counter += 1
                ext = mimetypes.guess_extension(mime) or ".bin"
                if ext == ".jpe":
                    ext = ".jpg"
                filename = f"attachment_{attach_counter:03d}{ext}"
                out_path = f"{rel_media_dir}/{filename}"
                try:
                    extra_outputs[out_path] = base64.b64decode(b64)
                except Exception:
                    continue
                # Rewrite source references: attachment:<name> → <rel_path>
                src = cell.source if isinstance(cell.source, str) else "".join(cell.source)
                src = src.replace(f"attachment:{att_name}", out_path)
                cell.source = src

    exporter = MarkdownExporter()
    body, resources = exporter.from_notebook_node(nb)

    # Merge attachment outputs with whatever nbconvert collected
    resources.setdefault("outputs", {}).update(extra_outputs)
    resources["output_extension"] = ".md"

    if no_images:
        # Suppress any binary outputs so FilesWriter doesn't drop them on disk.
        resources["outputs"] = {}
    elif filter_images:
        seen_hashes: set[str] = set()
        kept = {}
        dropped_paths: list[str] = []
        for rel_path, payload in resources["outputs"].items():
            if isinstance(payload, (bytes, bytearray)) and not should_keep_image_bytes(
                bytes(payload), seen_hashes=seen_hashes
            ):
                dropped_paths.append(rel_path)
                continue
            kept[rel_path] = payload
        resources["outputs"] = kept
        if dropped_paths:
            # Strip the corresponding image references from the markdown body.
            for path in dropped_paths:
                body = re.sub(
                    rf'!\[[^\]]*\]\({re.escape(path)}\)\s*\n?', '', body
                )

    writer = FilesWriter(build_directory=str(out_file.parent))
    writer.write(body, resources, notebook_name=out_file.stem)

    markdown = out_file.read_text(encoding="utf-8") if out_file.exists() else body
    if no_images:
        markdown = _strip_image_refs(markdown)
        out_file.write_text(markdown, encoding="utf-8")
        media_dir = None
    else:
        media_dir = out_file.parent / rel_media_dir
    _report_result(out_file, media_dir if media_dir and media_dir.exists() else None)
    return markdown


# ─────────────────────────────────────────────────────────────
# Pandoc fallback
# ─────────────────────────────────────────────────────────────

def _check_pandoc() -> bool:
    return shutil.which("pandoc") is not None


def _convert_with_pandoc(input_file: Path, out_file: Path, suffix: str, no_images: bool = False, filter_images: bool = False) -> str:
    if not _check_pandoc():
        print(f"[ERROR] Format '{suffix}' requires pandoc. Install it:")
        print("   macOS:   brew install pandoc")
        print("   Ubuntu:  sudo apt install pandoc")
        print("   Windows: https://pandoc.org/installing.html")
        return ""

    input_format, _ = PANDOC_FORMATS[suffix]
    rel_media_dir = f"{out_file.stem}_files"
    media_dir = out_file.parent / rel_media_dir

    cmd = [
        "pandoc",
        "-f", input_format,
        "-t", "gfm",
        str(input_file.resolve()),
        "-o", str(out_file.resolve()),
        "--wrap", "none",
        "--strip-comments",
    ]
    if suffix in PANDOC_MEDIA_FORMATS and not no_images:
        cmd.extend(["--extract-media", rel_media_dir])

    result = subprocess.run(cmd, capture_output=True, text=True,
                            cwd=str(out_file.parent))
    if result.returncode != 0:
        print(f"[ERROR] Pandoc conversion failed:\n{result.stderr}")
        return ""
    if not out_file.exists():
        print("[ERROR] Conversion completed but no output file was generated")
        return ""

    markdown = out_file.read_text(encoding="utf-8")

    # Flatten nested media/ subdir that pandoc creates
    nested_media = media_dir / "media"
    if nested_media.exists():
        for f in nested_media.iterdir():
            if f.is_file():
                shutil.move(str(f), str(media_dir / f.name))
        try:
            nested_media.rmdir()
        except OSError:
            pass
        markdown = markdown.replace(f"{rel_media_dir}/media/", f"{rel_media_dir}/")

    # Normalize absolute paths to relative
    for abs_str in (str(media_dir.resolve()).replace("\\", "/"),
                    str(media_dir.resolve())):
        if abs_str in markdown:
            markdown = markdown.replace(abs_str, rel_media_dir)

    markdown = _html_img_to_md(markdown)
    if no_images:
        markdown = _strip_image_refs(markdown)
        # In case pandoc still wrote a media dir for non-PANDOC_MEDIA_FORMATS
        if media_dir.exists():
            shutil.rmtree(media_dir, ignore_errors=True)
    elif filter_images and media_dir.exists():
        # Filter decorative images from the extracted media set
        seen_hashes: set[str] = set()
        for f in list(media_dir.rglob("*")):
            if not f.is_file():
                continue
            try:
                payload = f.read_bytes()
            except Exception:
                continue
            if not should_keep_image_bytes(payload, seen_hashes=seen_hashes):
                rel = f.relative_to(media_dir.parent).as_posix()
                # Drop ![](rel) references pointing at this file
                markdown = re.sub(
                    rf'!\[[^\]]*\]\({re.escape(rel)}\)\s*\n?', '', markdown
                )
                f.unlink(missing_ok=True)
        # Clean up empty media dir
        if not any(media_dir.iterdir()):
            media_dir.rmdir()
    out_file.write_text(markdown, encoding="utf-8")

    _report_result(out_file, media_dir if (not no_images and media_dir.exists()) else None)
    return markdown


# ─────────────────────────────────────────────────────────────
# Dispatcher
# ─────────────────────────────────────────────────────────────

_FORMAT_DESC = {
    ".docx":  "Microsoft Word (mammoth)",
    ".html":  "HTML (markdownify)",
    ".htm":   "HTML (markdownify)",
    ".epub":  "EPUB (ebooklib)",
    ".ipynb": "Jupyter Notebook (nbconvert)",
}


def convert_to_markdown(input_path: str, output_path: str | None = None, no_images: bool = False, filter_images: bool = False) -> str:
    input_file = Path(input_path)
    if not input_file.exists():
        print(f"[ERROR] File not found: {input_path}")
        return ""

    suffix = input_file.suffix.lower()
    if suffix not in NATIVE_FORMATS and suffix not in PANDOC_FORMATS:
        supported = ", ".join(sorted(NATIVE_FORMATS | PANDOC_FORMATS.keys()))
        print(f"[ERROR] Unsupported format: {suffix}")
        print(f"   Supported: {supported}")
        return ""

    out_file = Path(output_path) if output_path else input_file.with_suffix(".md")
    out_file.parent.mkdir(parents=True, exist_ok=True)

    if suffix in NATIVE_FORMATS:
        desc = _FORMAT_DESC[suffix]
        print(f"[INFO] Converting {desc}: {input_file.name}")
        try:
            if suffix == ".docx":
                return _convert_docx(input_file, out_file, no_images=no_images, filter_images=filter_images)
            if suffix in (".html", ".htm"):
                return _convert_html(input_file, out_file, no_images=no_images, filter_images=filter_images)
            if suffix == ".epub":
                return _convert_epub(input_file, out_file, no_images=no_images, filter_images=filter_images)
            if suffix == ".ipynb":
                return _convert_ipynb(input_file, out_file, no_images=no_images, filter_images=filter_images)
        except Exception as exc:
            print(f"[ERROR] Conversion failed: {exc}")
            return ""

    _, format_desc = PANDOC_FORMATS[suffix]
    print(f"[INFO] Converting {format_desc} via pandoc: {input_file.name}")
    try:
        return _convert_with_pandoc(input_file, out_file, suffix, no_images=no_images, filter_images=filter_images)
    except Exception as exc:
        print(f"[ERROR] Conversion failed: {exc}")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown "
                    "(pure-Python for common formats, pandoc fallback for the rest)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 doc_to_md.py lecture.docx                # Word → Markdown (mammoth)
  python3 doc_to_md.py article.html                # HTML → Markdown (markdownify)
  python3 doc_to_md.py book.epub                   # EPUB → Markdown (ebooklib)
  python3 doc_to_md.py notebook.ipynb              # Jupyter → Markdown (nbconvert)
  python3 doc_to_md.py manuscript.tex              # LaTeX → Markdown (pandoc fallback)

Native formats (no pandoc required):
  .docx  .html/.htm  .epub  .ipynb

Pandoc fallback formats (require system pandoc):
  .doc  .odt  .rtf  .tex/.latex  .rst  .org  .typ
        """,
    )
    parser.add_argument("input", help="Input document file")
    parser.add_argument("-o", "--output", help="Output Markdown file path")
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image extraction and strip image references from the Markdown",
    )
    parser.add_argument(
        "--filter-images",
        action="store_true",
        help="Filter decorative images (logos, tracking pixels, low-info blocks)",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Faithful reproduction (currently a no-op for native doc formats; reserved for future use)",
    )
    args = parser.parse_args()

    if args.no_images and args.filter_images:
        print("Error: --no-images and --filter-images are mutually exclusive.")
        sys.exit(2)

    result = convert_to_markdown(args.input, args.output, no_images=args.no_images, filter_images=args.filter_images)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
