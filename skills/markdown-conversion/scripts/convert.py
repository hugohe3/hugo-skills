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


def run_subprocess(cmd: list[str], label: str) -> int:
    print(f"[>>] Calling: {label}", flush=True)
    try:
        return subprocess.run(cmd, check=False).returncode
    except KeyboardInterrupt:
        return 130


def run_python_script(script_name: str, args: list[str]) -> int:
    script_path = get_script_path(script_name)
    if not script_path.exists():
        print(f"Error: Script not found: {script_path}")
        return 1

    cmd = [sys.executable, str(script_path)] + args
    return run_subprocess(cmd, f"{script_name} {' '.join(args)}".strip())


SKIP_SUFFIXES = MARKDOWN_SUFFIXES | TEXT_SUFFIXES | {".json", ".yaml", ".yml", ".log"}


def list_convertible_files(path: Path) -> list[Path]:
    """Return convertible files in a directory (one level), skipping md/txt/hidden/etc."""
    return sorted(
        f for f in path.iterdir()
        if f.is_file()
        and not f.name.startswith(".")
        and f.suffix.lower() not in SKIP_SUFFIXES
    )


def detect_type(input_arg: str) -> str:
    """Detect the input type from a file path, directory, or URL."""
    if input_arg.startswith(("http://", "https://")):
        return "pdf_url" if input_arg.lower().endswith(".pdf") else "web"

    path = Path(input_arg)
    if not path.exists():
        return "unknown"

    if path.is_dir():
        return "dir"

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


def mineru_local_paths(input_arg: str, output: str | None) -> tuple[list[str], Path, Path | None]:
    """Return MinerU output args, final Markdown path, and an optional generated path to rename."""
    input_path = Path(input_arg)
    default_md = input_path.parent / f"{input_path.stem}.md"
    if not output:
        return [], default_md, None

    requested = Path(output)
    if requested.suffix.lower() == ".md":
        output_dir = requested.parent if str(requested.parent) else Path(".")
        generated = output_dir / f"{input_path.stem}.md"
        rename_from = generated if generated.resolve() != requested.resolve() else None
        return ["-o", str(output_dir)], requested, rename_from

    output_dir = requested
    return ["-o", str(output_dir)], output_dir / f"{input_path.stem}.md", None


def rename_generated_output(generated: Path | None, requested: Path) -> int:
    if generated is None:
        return 0
    if not generated.exists():
        print(f"[ERROR] Expected MinerU output not found: {generated}")
        return 1
    requested.parent.mkdir(parents=True, exist_ok=True)
    generated.replace(requested)
    return 0


def reserve_batch_output(input_file: Path, out_root: Path, used_names: set[str]) -> Path:
    out_path = out_root / f"{input_file.stem}.md"
    if out_path.name in used_names:
        suffix = input_file.suffix.lower().lstrip(".") or "file"
        out_path = out_root / f"{input_file.stem}_{suffix}.md"
        counter = 2
        while out_path.name in used_names:
            out_path = out_root / f"{input_file.stem}_{suffix}_{counter}.md"
            counter += 1
    used_names.add(out_path.name)
    return out_path


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Unified Markdown Converter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 convert.py paper.pdf                 # PDF -> Markdown (local PyMuPDF, default)
  python3 convert.py paper.pdf --mineru        # PDF -> Markdown (MinerU cloud high-accuracy)
  python3 convert.py https://site.com/article  # Web -> Markdown (Python with curl_cffi)
  python3 convert.py report.docx               # Word -> Markdown
  python3 convert.py data.xlsx                 # Excel -> Markdown
  python3 convert.py deck.pptx                 # PowerPoint -> Markdown
  python3 convert.py ./video_course -t sub     # Subtitles -> Markdown
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
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image extraction across all backends (drops image references from output)",
    )
    parser.add_argument(
        "--filter-images",
        action="store_true",
        help="Filter decorative images (logos, tracking pixels, low-info blocks) — keeps information-bearing images",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Faithful reproduction: disable all heuristic cleaning (header/footer dedup, heading detection, web main-content extraction, subtitle paragraph anchors)",
    )
    parser.add_argument("-o", "--output", help="Output path")
    return parser.parse_known_args()


def dispatch_single(input_arg: str, conv_type: str, output: str | None, use_mineru: bool, no_images: bool, filter_images: bool, raw: bool, unknown_args: list[str]) -> int:
    """Dispatch one input (single file or URL) to the right converter. Returns exit code."""
    if conv_type == "sub":
        conv_type = "subtitle"
    if conv_type == "pdf_url":
        conv_type = "pdf"

    if conv_type == "markdown":
        print(f"[OK] Input is already Markdown: {input_arg}")
        print_output(input_arg)
        return 0

    if conv_type == "text":
        out = resolve_output(output, input_arg)
        src = Path(input_arg).read_text(encoding="utf-8", errors="replace")
        Path(out).write_text(src, encoding="utf-8")
        print(f"[OK] Plain text copied as Markdown: {out}")
        print_output(out)
        return 0

    if conv_type == "pdf":
        is_url = input_arg.startswith(("http://", "https://"))
        route_mineru = use_mineru or is_url
        if route_mineru:
            if is_url:
                out = output
                out_args = build_output_args(out)
                rename_from = None
            else:
                out_args, out_path, rename_from = mineru_local_paths(input_arg, output)
                out = str(out_path)
            if no_images:
                image_args = ["--no-images"]
            elif filter_images:
                image_args = ["--filter-images"]
            else:
                image_args = []
            raw_args = ["--raw"] if raw else []
            script_args = (["--url", input_arg] if is_url else [input_arg]) + out_args + image_args + raw_args + unknown_args
            rc = run_python_script("pdf_to_md_mineru.py", script_args)
        else:
            out = resolve_output(output, input_arg)
            rename_from = None
            # Map --no-images / --filter-images onto pdf_to_md.py's --images
            # tri-state; defer to any explicit --images in unknown_args.
            has_explicit_images = any(a == "--images" or a.startswith("--images=") for a in unknown_args)
            if has_explicit_images:
                image_args = []
            elif no_images:
                image_args = ["--images", "none"]
            elif filter_images:
                image_args = ["--images", "filtered"]
            else:
                image_args = []
            raw_args = ["--raw"] if raw else []
            script_args = [input_arg] + build_output_args(out) + image_args + raw_args + unknown_args
            rc = run_python_script("pdf_to_md.py", script_args)
        if rc != 0:
            return rc
        rc = rename_generated_output(rename_from, Path(out)) if out else 0
        if rc != 0:
            return rc
        if out and not (route_mineru and is_url):
            print_output(out)
        return 0

    image_args: list[str] = []
    if no_images:
        image_args = ["--no-images"]
    elif filter_images:
        image_args = ["--filter-images"]
    raw_args = ["--raw"] if raw else []

    if conv_type == "web":
        out = output
        script_args = [input_arg] + build_output_args(out) + image_args + raw_args + unknown_args
        rc = run_python_script("web_to_md.py", script_args)
        if rc != 0:
            return rc
        if out:
            print_output(out)
        return 0

    if conv_type == "doc":
        out = resolve_output(output, input_arg)
        script_args = [input_arg] + build_output_args(out) + image_args + raw_args + unknown_args
        rc = run_python_script("doc_to_md.py", script_args)
        if rc != 0:
            return rc
        print_output(out)
        return 0

    if conv_type == "excel":
        out = resolve_output(output, input_arg)
        script_args = [input_arg] + build_output_args(out) + unknown_args
        rc = run_python_script("excel_to_md.py", script_args)
        if rc != 0:
            return rc
        print_output(out)
        return 0

    if conv_type == "pptx":
        out = resolve_output(output, input_arg)
        script_args = [input_arg] + build_output_args(out) + image_args + raw_args + unknown_args
        rc = run_python_script("ppt_to_md.py", script_args)
        if rc != 0:
            return rc
        print_output(out)
        return 0

    if conv_type == "subtitle":
        out = resolve_output(output, input_arg) if Path(input_arg).is_file() else output
        script_args = [input_arg] + build_output_args(out) + raw_args + unknown_args
        rc = run_python_script("subtitle_to_md.py", script_args)
        if rc != 0:
            return rc
        return 0

    print(
        f"Error: Could not determine conversion type for '{input_arg}'. "
        "Please use -t/--type to specify one of: pdf, doc, excel, pptx, web, sub."
    )
    return 1


def batch_directory(input_dir: str, output_dir: str | None, use_mineru: bool, no_images: bool, filter_images: bool, raw: bool, unknown_args: list[str]) -> tuple[int, Path]:
    """Convert every convertible file in a directory. Returns (failures, output_root)."""
    in_path = Path(input_dir)
    files = list_convertible_files(in_path)
    out_root = Path(output_dir) if output_dir else in_path
    if not files:
        print(f"[ERROR] No convertible files in directory: {input_dir}")
        return 1, out_root

    out_root.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Batch mode: {len(files)} file(s) in {in_path}")
    succeeded = 0
    failures = 0
    skipped = 0
    used_outputs: set[str] = set()
    for i, f in enumerate(files, 1):
        per_type = detect_type(str(f))
        if per_type in {"unknown", "dir"}:
            print(f"  [{i}/{len(files)}] [SKIP] {f.name} (unsupported)")
            skipped += 1
            continue
        per_out = str(reserve_batch_output(f, out_root, used_outputs))
        print(f"  [{i}/{len(files)}] {f.name}")
        rc = dispatch_single(str(f), per_type, per_out, use_mineru, no_images, filter_images, raw, unknown_args)
        if rc == 0:
            succeeded += 1
        else:
            failures += 1
    print(
        f"[OK] Batch done: {succeeded} succeeded, "
        f"{failures} failed, {skipped} skipped"
    )
    return failures, out_root


def main() -> int:
    args, unknown_args = parse_args()
    conv_type = args.type

    if conv_type == "auto":
        conv_type = detect_type(args.input)

    # Mutually exclusive image flags
    if args.no_images and args.filter_images:
        print("Error: --no-images and --filter-images are mutually exclusive.")
        return 2

    if conv_type == "dir":
        failures, _ = batch_directory(args.input, args.output, args.mineru, args.no_images, args.filter_images, args.raw, unknown_args)
        return 0 if failures == 0 else 1

    return dispatch_single(args.input, conv_type, args.output, args.mineru, args.no_images, args.filter_images, args.raw, unknown_args)


if __name__ == "__main__":
    exit(main())
