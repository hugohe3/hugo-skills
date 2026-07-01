"""Batch input expansion helpers for markdown-conversion scripts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path


IsSupportedFile = Callable[[Path], bool]
IsExternalRef = Callable[[str], bool]


def expand_directory_inputs(
    inputs: list[str],
    is_supported_file: IsSupportedFile,
    is_external_ref: IsExternalRef | None = None,
) -> tuple[list[str], list[str], bool]:
    """Expand non-recursive directory inputs while preserving explicit inputs."""
    expanded: list[str] = []
    errors: list[str] = []
    saw_directory = False
    is_external = is_external_ref or (lambda _item: False)

    for item in inputs:
        if is_external(item):
            expanded.append(item)
            continue

        path = Path(item)
        if path.is_dir():
            saw_directory = True
            matches = sorted(
                child for child in path.iterdir()
                if child.is_file() and is_supported_file(child)
            )
            if matches:
                expanded.extend(str(match) for match in matches)
            else:
                errors.append(f"{item}: no supported files found")
            continue

        expanded.append(item)

    return expanded, errors, saw_directory


def _output_key(path: Path) -> Path:
    return path.resolve(strict=False)


def unique_output_path(output_dir: Path, stem: str, used_outputs: set[Path]) -> Path:
    """Return a unique Markdown output path for this process run."""
    base = stem or "output"
    candidate = output_dir / f"{base}.md"
    suffix = 2
    while _output_key(candidate) in used_outputs:
        candidate = output_dir / f"{base}_{suffix}.md"
        suffix += 1
    used_outputs.add(_output_key(candidate))
    return candidate
