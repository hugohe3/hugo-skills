#!/usr/bin/env python3
"""Markdown file merger.

Merges multiple Markdown files in a directory into a single document.
"""

import argparse
import re
from pathlib import Path


def natural_sort_key(s: str) -> list[str | int]:
    """Key function for natural (human-friendly) sort order."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(s))]


def read_md_file(file_path: Path) -> str:
    """Read a Markdown file, returning empty string on error."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"  [WARN] Failed to read {file_path.name}: {e}")
        return ""


def merge_markdown(
    input_dir: str,
    output_file: str = "merged.md",
    add_separator: bool = True,
    add_header: bool = True,
    recursive: bool = False
) -> None:
    """Merge Markdown files from a directory into a single document."""
    input_path = Path(input_dir)

    if not input_path.exists() or not input_path.is_dir():
        print(f"[ERROR] Directory not found: {input_dir}")
        return

    if recursive:
        md_files = list(input_path.rglob('*.md'))
    else:
        md_files = list(input_path.glob('*.md'))

    md_files.sort(key=lambda x: natural_sort_key(str(x)))

    output_path = input_path / output_file
    md_files = [f for f in md_files if f.resolve() != output_path.resolve()]

    if not md_files:
        print(f"[ERROR] No Markdown files found in: {input_dir}")
        return

    print(f"[INFO] Found {len(md_files)} files")

    merged_content = []

    for i, md_file in enumerate(md_files, 1):
        file_name = md_file.stem
        relative_path = md_file.relative_to(input_path)
        
        print(f"  [{i}/{len(md_files)}] {relative_path}")

        content = read_md_file(md_file)

        if not content.strip():
            print(f"    [SKIP] Empty file")
            continue

        if add_header:
            if recursive:
                header = f"## {relative_path}\n\n"
            else:
                header = f"## {file_name}\n\n"
            merged_content.append(header)

        merged_content.append(content.strip())

        if add_separator and i < len(md_files):
            merged_content.append("\n\n---\n\n")
        else:
            merged_content.append("\n\n")

    try:
        with open(output_path, 'w', encoding='utf-8') as output:
            output.write('\n'.join(merged_content))
        print(f"[OK] Merged output: {output_path}")
    except Exception as e:
        print(f"[ERROR] Write failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Merge multiple Markdown files into one document',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python merge_md.py ./notes
  python merge_md.py ./notes -o combined.md
  python merge_md.py ./docs -r --no-separator
        '''
    )
    
    parser.add_argument('input', help='input directory containing Markdown files')
    parser.add_argument('-o', '--output', default='merged.md', help='output filename (default: merged.md)')
    parser.add_argument('-r', '--recursive', action='store_true', help='process subdirectories recursively')
    parser.add_argument('--no-header', action='store_true', help='omit filename headers between files')
    parser.add_argument('--no-separator', action='store_true', help='omit horizontal separators between files')
    
    args = parser.parse_args()
    
    merge_markdown(
        args.input,
        args.output,
        add_separator=not args.no_separator,
        add_header=not args.no_header,
        recursive=args.recursive
    )
    return 0


if __name__ == "__main__":
    exit(main())
