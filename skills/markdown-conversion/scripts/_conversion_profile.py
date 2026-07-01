"""Shared output profiling helpers for markdown-conversion scripts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


IMAGE_MANIFEST_NAME = "image_manifest.json"
CONVERSION_PROFILE_SUFFIX = ".conversion_profile.json"
SOURCE_PROFILE_NAME = "source_profile.json"


def default_asset_dir(markdown_path: Path) -> Path:
    """Return the conventional companion asset directory for a Markdown file."""
    return markdown_path.parent / f"{markdown_path.stem}_files"


def _display_path(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _count_tables(lines: list[str]) -> int:
    count = 0
    in_table = False
    for line in lines:
        stripped = line.strip()
        is_table_line = stripped.startswith("|") and stripped.endswith("|")
        has_separator = bool(
            re.match(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$", stripped)
        )
        if is_table_line or has_separator:
            if not in_table:
                count += 1
                in_table = True
        else:
            in_table = False
    return count


def markdown_stats(markdown_path: Path) -> dict[str, int]:
    """Return lightweight Markdown structure counts."""
    if not markdown_path.exists():
        return {
            "line_count": 0,
            "char_count": 0,
            "heading_count": 0,
            "table_count": 0,
            "image_ref_count": 0,
            "link_count": 0,
        }
    text = markdown_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    return {
        "line_count": len(lines),
        "char_count": len(text),
        "heading_count": sum(1 for line in lines if re.match(r"^#{1,6}\s+", line)),
        "table_count": _count_tables(lines),
        "image_ref_count": len(re.findall(r"!\[[^\]]*\]\([^)]+\)", text)),
        "link_count": len(re.findall(r"(?<!!)\[[^\]]+\]\([^)]+\)", text)),
    }


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def profile_path_for(markdown_path: str | Path) -> Path:
    """Return the per-Markdown conversion profile path."""
    markdown = Path(markdown_path)
    return markdown.with_suffix(CONVERSION_PROFILE_SUFFIX)


def build_source_profile(
    *,
    input_path: str,
    markdown_path: str,
    converter: str,
    conversion_type: str,
    asset_dir: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Build a machine-readable profile for one converted source."""
    markdown = Path(markdown_path)
    root = markdown.parent
    is_url = input_path.startswith(("http://", "https://"))
    source = Path(input_path) if not is_url else None
    assets = Path(asset_dir) if asset_dir else default_asset_dir(markdown)
    image_manifest = assets / IMAGE_MANIFEST_NAME
    manifest_payload = read_json(image_manifest)
    image_count = 0
    if isinstance(manifest_payload, list):
        image_count = len(manifest_payload)
    elif isinstance(manifest_payload, dict):
        items = manifest_payload.get("items")
        image_count = len(items) if isinstance(items, list) else 0

    source_exists = bool(source and source.exists())
    profile = {
        "schema": "markdown-conversion.conversion_profile.v1",
        "converter": converter,
        "conversion_type": conversion_type,
        "source": {
            "path": input_path if is_url else _display_path(source, root),
            "name": input_path if is_url else (source.name if source and source.name else input_path),
            "suffix": "" if is_url else (source.suffix.lower() if source else ""),
            "kind": "url" if is_url else "file",
            "exists": source_exists,
            "size_bytes": source.stat().st_size if source_exists and source and source.is_file() else None,
        },
        "outputs": {
            "markdown": _display_path(markdown, root),
            "asset_dir": _display_path(assets, root) if assets.exists() else "",
            "image_manifest": _display_path(image_manifest, root) if image_manifest.exists() else "",
            "image_count": image_count,
        },
        "markdown": markdown_stats(markdown),
        "warnings": warnings or [],
    }
    return profile


def write_source_profile(
    *,
    input_path: str,
    markdown_path: str,
    converter: str,
    conversion_type: str,
    asset_dir: str | None = None,
    warnings: list[str] | None = None,
) -> Path:
    """Write a per-Markdown conversion profile beside the output."""
    markdown = Path(markdown_path)
    profile_path = profile_path_for(markdown)
    profile = build_source_profile(
        input_path=input_path,
        markdown_path=markdown_path,
        converter=converter,
        conversion_type=conversion_type,
        asset_dir=asset_dir,
        warnings=warnings,
    )
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return profile_path


def build_result_payload(
    *,
    input_path: str,
    markdown_path: str,
    converter: str,
    conversion_type: str,
    asset_dir: str | None = None,
    source_profile: str | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Return a compact JSON result for CLI consumers."""
    markdown = Path(markdown_path)
    assets = Path(asset_dir) if asset_dir else default_asset_dir(markdown)
    image_manifest = assets / IMAGE_MANIFEST_NAME
    profile = str(Path(source_profile).resolve()) if source_profile else ""
    return {
        "input": str(Path(input_path).resolve()) if not input_path.startswith(("http://", "https://")) else input_path,
        "markdown": str(markdown.resolve()),
        "asset_dir": str(assets.resolve()) if assets.exists() else "",
        "image_manifest": str(image_manifest.resolve()) if image_manifest.exists() else "",
        "conversion_profile": profile,
        "source_profile": profile,
        "converter": converter,
        "conversion_type": conversion_type,
        "warnings": warnings or [],
    }
