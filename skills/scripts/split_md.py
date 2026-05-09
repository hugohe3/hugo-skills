#!/usr/bin/env python3
"""Markdown file splitter.

Splits a large Markdown file into separate files by top-level heading (# Title).
"""

import argparse
import re
from pathlib import Path


def sanitize_filename(name: str) -> str:
    """Sanitize a filename by removing characters that are invalid on most filesystems."""
    # Remove characters invalid on most filesystems
    name = re.sub(r'[\\/*?:"<>|]', '', name)
    name = name.strip()
    return name


def split_md_by_h1(md_path: str, output_dir: str | None = None) -> None:
    """Split a Markdown file into separate files by top-level heading.

    Args:
        md_path: Path to the Markdown file.
        output_dir: Output directory (default: <stem>_split alongside the input).
    """
    md_path = Path(md_path)
    
    if not md_path.exists():
        print(f"[ERROR] File not found: {md_path}")
        return

    if output_dir:
        output_path = Path(output_dir)
    else:
        output_path = md_path.parent / f"{md_path.stem}_split"
    
    output_path.mkdir(parents=True, exist_ok=True)

    content = md_path.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Regex for H1 headings
    h1_pattern = re.compile(r'^#\s+(.+)$')

    # Find all H1 positions
    chapters = []
    for i, line in enumerate(lines):
        match = h1_pattern.match(line)
        if match:
            title = match.group(1).strip()
            # Skip known table-of-contents titles
            if title.lower() in ['目录', 'table of contents', 'contents']:
                continue
                
            chapters.append({
                'line_num': i,
                'title': title
            })
    
    if not chapters:
        print("[ERROR] No H1 headings found")
        return

    print(f"[FILE] Processing: {md_path.name}")
    print(f"[DIR] Output: {output_path}")
    print(f"[INFO] Found {len(chapters)} H1 sections")

    # Handle preamble before the first heading
    if chapters[0]['line_num'] > 0:
        preface_content = '\n'.join(lines[:chapters[0]['line_num']]).strip()
        if preface_content:
            preface_file = output_path / "00-preface.md"
            preface_file.write_text(preface_content, encoding='utf-8')
            print(f"  [OK] 00-preface.md")

    # Write each section to its own file
    for i, ch in enumerate(chapters):
        start_line = ch['line_num']

        # End line: start of next section, or EOF
        if i + 1 < len(chapters):
            end_line = chapters[i + 1]['line_num']
        else:
            end_line = len(lines)

        chapter_content = '\n'.join(lines[start_line:end_line]).strip()

        title = sanitize_filename(ch['title'])
        # Truncate long titles
        if len(title) > 50:
            title = title[:47] + "..."

        filename = f"{i+1:02d}-{title}.md"
        
        chapter_file = output_path / filename
        chapter_file.write_text(chapter_content, encoding='utf-8')
        print(f"  [OK] {filename}")
    
    print(f"\n[OK] Split complete: {len(chapters) + (1 if chapters[0]['line_num'] > 0 else 0)} files written")

    # Generate index.md
    index_content = f"# {md_path.stem} — Index\n\n"
    if chapters[0]['line_num'] > 0:
        index_content += f"- [Preface](00-preface.md)\n"
    for i, ch in enumerate(chapters):
        title = sanitize_filename(ch['title'])
        if len(title) > 50: title = title[:47] + "..."
        filename = f"{i+1:02d}-{title}.md"
        index_content += f"- [{ch['title']}]({filename})\n"

    (output_path / "index.md").write_text(index_content, encoding='utf-8')
    print(f"  [OK] index.md")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Split a Markdown file by top-level headings',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('input', help='input Markdown file path')
    parser.add_argument('-o', '--output', help='output directory (default: <stem>_split)')

    args = parser.parse_args()
    split_md_by_h1(args.input, args.output)
    return 0


if __name__ == '__main__':
    exit(main())
