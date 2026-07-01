#!/usr/bin/env python3
"""Unified Markdown converter.

Auto-detects source type and dispatches to the backend converter. The
dispatcher supports explicit multi-file inputs, non-recursive directory
expansion, URLs, Markdown/text passthrough, and backend-specific flag pass-through.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _batch import expand_directory_inputs, unique_output_path  # noqa: E402
from _conversion_profile import (  # noqa: E402
    build_result_payload,
    profile_path_for,
    write_source_profile,
)
from _dispatcher import (  # noqa: E402
    default_markdown_path,
    detect_source_type,
    is_supported_directory_item,
    is_url,
    resolve_route,
)


SCRIPT_DIR = Path(__file__).parent


def _print_status(message: str) -> None:
    print(message, file=sys.stderr)


def get_script_path(script_name: str) -> Path:
    return SCRIPT_DIR / script_name


def run_subprocess(cmd: list[str], label: str) -> int:
    _print_status(f"[>>] Calling: {label}")
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except KeyboardInterrupt:
        return 130

    if result.stdout.strip():
        print(result.stdout.strip(), file=sys.stderr)
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return result.returncode


def run_python_script(script_name: str, args: list[str]) -> int:
    script_path = get_script_path(script_name)
    if not script_path.exists():
        print(f"[ERROR] Script not found: {script_path}", file=sys.stderr)
        return 1
    cmd = [sys.executable, str(script_path)] + args
    return run_subprocess(cmd, f"{script_name} {' '.join(args)}".strip())


def resolve_output(output_arg: str | None, input_arg: str) -> Path:
    return Path(output_arg) if output_arg else default_markdown_path(input_arg)


def build_output_args(output_path: str | Path | None) -> list[str]:
    return ["-o", str(output_path)] if output_path else []


def print_output(path: str | Path) -> None:
    print(f"OUTPUT: {Path(path).resolve()}")


def write_profile(input_arg: str, output_path: str | Path, converter: str, conv_type: str) -> Path:
    """Write a conversion profile for one successful conversion."""
    return write_source_profile(
        input_path=input_arg,
        markdown_path=str(output_path),
        converter=converter,
        conversion_type=conv_type,
    )


def ensure_profile(input_arg: str, output_path: str | Path, converter: str, conv_type: str) -> Path:
    """Return an existing backend profile or write one if the backend skipped it."""
    profile_path = profile_path_for(output_path)
    if profile_path.is_file():
        return profile_path
    return write_profile(input_arg, output_path, converter, conv_type)


def print_json_result(
    input_arg: str,
    output_path: str | Path,
    converter: str,
    conv_type: str,
    profile_path: Path | None,
) -> None:
    payload = build_result_payload(
        input_path=input_arg,
        markdown_path=str(output_path),
        converter=converter,
        conversion_type=conv_type,
        source_profile=str(profile_path) if profile_path else None,
    )
    print(json.dumps(payload, ensure_ascii=False))


def mineru_local_paths(input_arg: str, output: str | None) -> tuple[list[str], Path, Path | None]:
    """Return MinerU CLI args, final Markdown path, and optional generated path to rename."""
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
        print(f"[ERROR] Expected MinerU output not found: {generated}", file=sys.stderr)
        return 1
    requested.parent.mkdir(parents=True, exist_ok=True)
    generated.replace(requested)
    return 0


def _image_args(no_images: bool, filter_images: bool) -> list[str]:
    if no_images:
        return ["--no-images"]
    if filter_images:
        return ["--filter-images"]
    return []


def _pdf_image_args(no_images: bool, filter_images: bool, unknown_args: list[str]) -> list[str]:
    has_explicit_images = any(arg == "--images" or arg.startswith("--images=") for arg in unknown_args)
    if has_explicit_images:
        return []
    if no_images:
        return ["--images", "none"]
    if filter_images:
        return ["--images", "filtered"]
    return []


def write_passthrough(input_arg: str, output: Path, conv_type: str, json_output: bool) -> int:
    """Copy Markdown/text-like input and write a conversion profile."""
    source = Path(input_arg)
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"[ERROR] Cannot read {source}: {exc}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.resolve() != source.resolve():
        output.write_text(text, encoding="utf-8")

    profile_path = write_profile(input_arg, output, "convert.py", conv_type)
    _print_status(f"[OK] Saved Markdown to: {output}")
    _print_status(f"   Wrote conversion profile -> {profile_path}")
    print_output(output)
    if json_output:
        print_json_result(input_arg, output, "convert.py", conv_type, profile_path)
    return 0


def dispatch_single(
    input_arg: str,
    conv_type: str,
    output: str | None,
    use_mineru: bool,
    no_images: bool,
    filter_images: bool,
    raw: bool,
    unknown_args: list[str],
    json_output: bool = False,
    web_output_dir: str | None = None,
) -> int:
    """Dispatch one input to the right converter. Returns a process exit code."""
    route = resolve_route(input_arg, conv_type)
    conv_type = route.conversion_type

    if conv_type in {"markdown", "text"}:
        return write_passthrough(input_arg, resolve_output(output, input_arg), conv_type, json_output)

    if conv_type in {"directory", "unknown"} or not route.script_name:
        print(
            f"[ERROR] Could not determine conversion type for {input_arg!r}. "
            "Use -t pdf|doc|excel|pptx|web|sub.",
            file=sys.stderr,
        )
        return 1

    if not is_url(input_arg) and not Path(input_arg).exists():
        print(f"[ERROR] File not found: {input_arg}", file=sys.stderr)
        return 1

    raw_args = ["--raw"] if raw else []

    if conv_type == "pdf":
        route_mineru = use_mineru or is_url(input_arg)
        if route_mineru:
            if is_url(input_arg):
                out_path = Path(output) if output else None
                out_args = build_output_args(out_path)
                rename_from = None
            else:
                out_args, out_path, rename_from = mineru_local_paths(input_arg, output)

            image_args = _image_args(no_images, filter_images)
            script_args = (
                (["--url", input_arg] if is_url(input_arg) else [input_arg])
                + out_args
                + image_args
                + raw_args
                + unknown_args
            )
            rc = run_python_script("pdf_to_md_mineru.py", script_args)
            converter = "pdf_to_md_mineru.py"
        else:
            out_path = resolve_output(output, input_arg)
            rename_from = None
            script_args = (
                [input_arg]
                + build_output_args(out_path)
                + _pdf_image_args(no_images, filter_images, unknown_args)
                + raw_args
                + unknown_args
            )
            rc = run_python_script("pdf_to_md.py", script_args)
            converter = "pdf_to_md.py"

        if rc != 0:
            return rc
        if out_path is not None:
            rc = rename_generated_output(rename_from, out_path)
            if rc != 0:
                return rc
            if out_path.is_file():
                profile_path = ensure_profile(input_arg, out_path, converter, "pdf")
                print_output(out_path)
                if json_output:
                    print_json_result(input_arg, out_path, converter, "pdf", profile_path)
        return 0

    if conv_type == "web":
        out_path = Path(output) if output else None
        emit_result: Path | None = None
        extra_args = list(unknown_args)
        if out_path is None:
            emit_file = tempfile.NamedTemporaryFile(
                prefix="markdown-conversion-web-result-",
                suffix=".json",
                delete=False,
            )
            emit_file.close()
            emit_result = Path(emit_file.name)
            extra_args.extend(["--emit-result", str(emit_result)])
        dir_args = ["-d", web_output_dir] if out_path is None and web_output_dir else []
        script_args = (
            [input_arg]
            + build_output_args(out_path)
            + dir_args
            + _image_args(no_images, filter_images)
            + raw_args
            + extra_args
        )
        rc = run_python_script("web_to_md.py", script_args)
        if rc != 0:
            if emit_result:
                emit_result.unlink(missing_ok=True)
            return rc
        if out_path is None and emit_result is not None:
            out_path = _read_emitted_markdown_path(emit_result)
            emit_result.unlink(missing_ok=True)
        if out_path and out_path.is_file():
            profile_path = ensure_profile(input_arg, out_path, "web_to_md.py", "web")
            print_output(out_path)
            if json_output:
                print_json_result(input_arg, out_path, "web_to_md.py", "web", profile_path)
            return 0
        print("[ERROR] Web conversion did not produce a Markdown output path", file=sys.stderr)
        if out_path:
            print(f"[ERROR] Expected Markdown output not found: {out_path}", file=sys.stderr)
        return 1

    out_path = resolve_output(output, input_arg)
    if conv_type == "excel":
        script_args = [input_arg] + build_output_args(out_path) + unknown_args
    elif conv_type == "subtitle":
        script_args = [input_arg] + build_output_args(out_path) + raw_args + unknown_args
    else:
        script_args = [input_arg] + build_output_args(out_path) + _image_args(no_images, filter_images) + raw_args + unknown_args

    rc = run_python_script(route.script_name, script_args)
    if rc != 0:
        return rc
        if out_path.is_file():
            profile_path = ensure_profile(input_arg, out_path, route.script_name, conv_type)
            print_output(out_path)
            if json_output:
                print_json_result(input_arg, out_path, route.script_name, conv_type, profile_path)
    return 0


def _read_emitted_markdown_path(path: Path) -> Path | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    markdown = payload.get("markdown")
    return Path(markdown) if isinstance(markdown, str) and markdown else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Auto-detect source type and convert to Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 convert.py paper.pdf
  python3 convert.py paper.pdf report.docx deck.pptx
  python3 convert.py ./mixed_docs -o ./out
  python3 convert.py paper.pdf --mineru
  python3 convert.py https://site.com/article
  python3 convert.py ./video_course -t sub

Backend-specific flags not listed here are passed through to the selected
converter, so existing converter behavior remains the source of truth.
        """,
    )
    parser.add_argument("inputs", nargs="+", help="Input file(s), directories, or URL(s)")
    parser.add_argument(
        "-t",
        "--type",
        choices=["pdf", "doc", "excel", "pptx", "web", "sub", "markdown", "text", "auto"],
        default="auto",
        help="Force a specific conversion type",
    )
    parser.add_argument(
        "--mineru",
        action="store_true",
        help="Use MinerU cloud parser instead of local parser for PDF inputs",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Skip image extraction across image-capable backends",
    )
    parser.add_argument(
        "--filter-images",
        action="store_true",
        help="Filter decorative images while keeping information-bearing images",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Disable heuristic cleaning where a backend supports it",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output Markdown file for one input, or output directory for multiple inputs/directories",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable conversion result after success",
    )
    return parser


def _validate_image_options(args: argparse.Namespace) -> bool:
    if args.no_images and args.filter_images:
        print("[ERROR] --no-images and --filter-images are mutually exclusive.", file=sys.stderr)
        return False
    return True


def _resolve_output_arg(
    input_arg: str,
    conversion_type: str,
    output_arg: str | None,
    batch_mode: bool,
    used_outputs: set[Path],
) -> str | None:
    if conversion_type == "subtitle" and not is_url(input_arg) and Path(input_arg).is_dir():
        return output_arg
    if conversion_type == "web" and not output_arg:
        return None
    if not output_arg:
        return str(default_markdown_path(input_arg))
    if batch_mode:
        if conversion_type == "web":
            return None
        return str(unique_output_path(Path(output_arg), default_markdown_path(input_arg).stem, used_outputs))
    return output_arg


def dispatch_many(
    inputs: list[str],
    args: argparse.Namespace,
    unknown_args: list[str],
    initial_failures: list[str] | None = None,
    saw_directory: bool = False,
) -> int:
    batch_mode = saw_directory or len(inputs) > 1
    if args.output and batch_mode:
        output_dir = Path(args.output)
        if output_dir.exists() and not output_dir.is_dir():
            print(f"[ERROR] Batch output path is not a directory: {args.output}", file=sys.stderr)
            return 1
        output_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    failed: list[str] = []
    skipped: list[str] = list(initial_failures or [])
    used_outputs: set[Path] = set()

    for input_arg in inputs:
        route = resolve_route(input_arg, args.type)
        output_arg = _resolve_output_arg(
            input_arg,
            route.conversion_type,
            args.output,
            batch_mode,
            used_outputs,
        )
        if batch_mode:
            _print_status(f"\n==> {input_arg}")

        rc = dispatch_single(
            input_arg,
            route.conversion_type,
            output_arg,
            args.mineru,
            args.no_images,
            args.filter_images,
            args.raw,
            unknown_args,
            json_output=args.json,
            web_output_dir=args.output if batch_mode and route.conversion_type == "web" else None,
        )
        if rc == 0:
            success_count += 1
        else:
            failed.append(f"{input_arg}: exit {rc}")

    if batch_mode:
        _print_status(f"\n[Done] Success: {success_count}/{len(inputs)}, Failed: {len(failed)}")
        if skipped:
            _print_status("\n[Skipped directories]:")
            for item in skipped:
                _print_status(f"  - {item}")
        if failed:
            _print_status("\n[Failed inputs]:")
            for item in failed:
                _print_status(f"  - {item}")

    if not inputs:
        return 1
    return 0 if not failed and not skipped else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args, unknown_args = parser.parse_known_args(argv)

    if not _validate_image_options(args):
        return 2

    if args.type == "sub":
        inputs = args.inputs
        expansion_errors: list[str] = []
        saw_directory = any((not is_url(item)) and Path(item).is_dir() for item in inputs)
    else:
        inputs, expansion_errors, saw_directory = expand_directory_inputs(
            args.inputs,
            is_supported_directory_item,
            is_external_ref=is_url,
        )

    if unknown_args:
        passthrough_types = {
            resolve_route(item, args.type).conversion_type
            for item in inputs
            if detect_source_type(item) in {"markdown", "text"} or args.type in {"markdown", "text"}
        }
        if passthrough_types:
            print(
                "[ERROR] Backend-specific flags cannot be used with markdown/text passthrough inputs",
                file=sys.stderr,
            )
            return 2

    return dispatch_many(
        inputs,
        args,
        unknown_args,
        initial_failures=expansion_errors,
        saw_directory=saw_directory,
    )


if __name__ == "__main__":
    raise SystemExit(main())
