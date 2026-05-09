#!/usr/bin/env python3
"""
Unified Markdown Converter

Auto-detects the input type and dispatches to the appropriate conversion script.
Supports: PDF, Word/EPUB/HTML, Excel, PowerPoint, web pages, and subtitles.
"""

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
SUBTITLE_SUFFIXES = {".srt", ".vtt", ".ass"}
DOC_SUFFIXES = {".docx", ".doc", ".odt", ".rtf", ".epub", ".html", ".htm", ".ipynb",
                ".tex", ".latex", ".rst", ".org", ".typ"}
EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
PPTX_SUFFIXES = {".pptx", ".pptm", ".ppsx", ".ppsm", ".potx", ".potm"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
TEXT_SUFFIXES = {".txt", ".text"}


def get_script_path(script_name: str) -> Path:
    return SCRIPT_DIR / script_name


def run_subprocess(cmd: list[str], label: str) -> None:
    print(f"[>>] Calling: {label}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
    except KeyboardInterrupt:
        sys.exit(130)


def run_python_script(script_name: str, args: list[str]) -> None:
    script_path = get_script_path(script_name)
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}")
        sys.exit(1)

    cmd = [sys.executable, str(script_path)] + args
    run_subprocess(cmd, f"{script_name} {' '.join(args)}".strip())


def directory_contains_subtitles(path: Path) -> bool:
    try:
        return any(child.suffix.lower() in SUBTITLE_SUFFIXES for child in path.iterdir() if child.is_file())
    except OSError:
        return False


def detect_type(input_arg: str) -> str:
    """Detect the input type from a file path, directory, or URL."""
    if input_arg.startswith(("http://", "https://")):
        return "pdf_url" if input_arg.lower().endswith(".pdf") else "web"

    path = Path(input_arg)
    if not path.exists():
        return "unknown"

    if path.is_dir():
        return "subtitle" if directory_contains_subtitles(path) else "dir"

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in SUBTITLE_SUFFIXES:
        return "subtitle"
    if suffix in EXCEL_SUFFIXES:
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


def default_output_path(input_path: str) -> str:
    """Return default output .md path alongside the input file."""
    p = Path(input_path)
    return str(p.parent / (p.stem + ".md"))


def resolve_output(output_arg: str | None, input_path: str) -> str:
    """Return the resolved output path (explicit or default)."""
    return output_arg if output_arg else default_output_path(input_path)


def build_output_args(output_path: str | None) -> list[str]:
    return ["-o", output_path] if output_path else []


def print_output(path: str) -> None:
    print(f"OUTPUT: {Path(path).resolve()}")


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Unified Markdown Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python convert.py paper.pdf                 # PDF -> Markdown (local PyMuPDF, default)
  python convert.py paper.pdf --mineru        # PDF -> Markdown (MinerU cloud high-accuracy)
  python convert.py https://site.com/article  # Web -> Markdown (Python with curl_cffi)
  python convert.py report.docx               # Word -> Markdown
  python convert.py data.xlsx                 # Excel -> Markdown
  python convert.py deck.pptx                 # PowerPoint -> Markdown
  python convert.py ./video_course -t sub     # Subtitles -> Markdown
        """,
    )

    parser.add_argument("input", help="Input file, directory, or URL")
    parser.add_argument(
        "-t",
        "--type",
        choices=["pdf", "doc", "excel", "pptx", "web", "sub", "auto"],
        default="auto",
        help="Force specific conversion type",
    )
    parser.add_argument(
        "--mineru",
        action="store_true",
        help="Use MinerU cloud parser instead of local parser (PDF only)",
    )
    parser.add_argument("-o", "--output", help="Output path")
    return parser.parse_known_args()


def main() -> int:
    args, unknown_args = parse_args()
    conv_type = args.type

    if conv_type == "auto":
        conv_type = detect_type(args.input)

    if conv_type == "sub":
        conv_type = "subtitle"

    if conv_type == "markdown":
        print(f"[OK] Input is already Markdown: {args.input}")
        print_output(args.input)
        return 0

    if conv_type == "pdf_url":
        conv_type = "pdf"

    if conv_type == "text":
        out = resolve_output(args.output, args.input)
        src = Path(args.input).read_text(encoding="utf-8", errors="replace")
        Path(out).write_text(src, encoding="utf-8")
        print(f"[OK] Plain text copied as Markdown: {out}")
        print_output(out)
        return 0

    if conv_type == "pdf":
        is_url = args.input.startswith(("http://", "https://"))
        use_mineru = args.mineru or is_url
        out = resolve_output(args.output, args.input) if not is_url else args.output
        if use_mineru:
            out_args = build_output_args(out)
            script_args = (["--url", args.input] if is_url else [args.input]) + out_args + unknown_args
            run_python_script("pdf_to_md_mineru.py", script_args)
        else:
            script_args = [args.input] + build_output_args(out) + unknown_args
            run_python_script("pdf_to_md.py", script_args)
        if out:
            print_output(out)
        return 0

    if conv_type == "web":
        out = args.output
        script_args = [args.input] + build_output_args(out)
        run_python_script("web_to_md.py", script_args)
        if out:
            print_output(out)
        return 0

    if conv_type in {"doc", "dir"}:
        out = resolve_output(args.output, args.input) if conv_type == "doc" else args.output
        script_args = [args.input] + build_output_args(out) + unknown_args
        run_python_script("doc_to_md.py", script_args)
        if out and conv_type == "doc":
            print_output(out)
        return 0

    if conv_type == "excel":
        out = resolve_output(args.output, args.input)
        script_args = [args.input] + build_output_args(out) + unknown_args
        run_python_script("excel_to_md.py", script_args)
        print_output(out)
        return 0

    if conv_type == "pptx":
        out = resolve_output(args.output, args.input)
        script_args = [args.input] + build_output_args(out) + unknown_args
        run_python_script("ppt_to_md.py", script_args)
        print_output(out)
        return 0

    if conv_type == "subtitle":
        out = resolve_output(args.output, args.input) if Path(args.input).is_file() else args.output
        script_args = [args.input] + build_output_args(out) + unknown_args
        run_python_script("subtitle_to_md.py", script_args)
        if out and Path(args.input).is_file():
            print_output(out)
        return 0

    print(
        f"Error: Could not determine conversion type for '{args.input}'. "
        "Please use -t/--type to specify one of: pdf, doc, excel, pptx, web, sub."
    )
    return 1


if __name__ == "__main__":
    exit(main())
