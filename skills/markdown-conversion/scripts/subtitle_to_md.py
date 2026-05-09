#!/usr/bin/env python3
"""Subtitle to Markdown converter.

Converts SRT/VTT subtitle files (single file or course directory) to Markdown.
Strips timestamps and outputs clean transcript text.
"""

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path


SUBTITLE_SUFFIXES = {'.srt', '.vtt', '.ass'}
HTML_SUFFIXES = {'.html', '.htm'}


class HTMLTextExtractor(HTMLParser):
    """Extract plain text from HTML content."""
    
    def __init__(self) -> None:
        super().__init__()
        self.text_parts = []
        self.skip_tags = {'script', 'style'}
        self.current_skip = False
    
    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.current_skip = True
        elif tag in ('p', 'br', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'):
            self.text_parts.append('\n')
    
    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.current_skip = False
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.text_parts.append('\n')
    
    def handle_data(self, data):
        if not self.current_skip:
            self.text_parts.append(data)
    
    def get_text(self) -> str:
        text = ''.join(self.text_parts)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()


def html_to_text(content: str) -> str:
    """Convert HTML to plain text, handling entities and block-level structure."""
    content = content.replace('&nbsp;', ' ')
    content = content.replace('&amp;', '&')
    content = content.replace('&lt;', '<')
    content = content.replace('&gt;', '>')
    content = content.replace('&quot;', '"')
    
    parser = HTMLTextExtractor()
    try:
        parser.feed(content)
        return parser.get_text()
    except Exception:
        text = re.sub(r'<[^>]+>', ' ', content)
        return re.sub(r'\s+', ' ', text).strip()


def process_srt_content(content: str) -> str:
    """Parse SRT subtitle content and return clean transcript text."""
    lines = content.split('\n')
    processed_text = []
    i = 0

    while i < len(lines):
        if i < len(lines) and '-->' in lines[i]:
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            text_chunk = []
            while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                if not lines[i].strip().isdigit():
                    text_chunk.append(lines[i].strip())
                i += 1
            if text_chunk:
                processed_text.append(' '.join(text_chunk))
        else:
            i += 1

    return ' '.join(processed_text)


def process_vtt_content(content: str) -> str:
    """Parse VTT subtitle content and return clean transcript text."""
    lines = content.split('\n')
    start_index = 0

    for i, line in enumerate(lines):
        if line.strip() == 'WEBVTT' or line.startswith('WEBVTT '):
            start_index = i + 1
            while start_index < len(lines) and (lines[start_index].strip() == '' or ':' in lines[start_index]):
                start_index += 1
            break

    processed_text = []
    i = start_index

    while i < len(lines):
        if i < len(lines) and '-->' in lines[i]:
            i += 1
            text_chunk = []
            while i < len(lines) and lines[i].strip() and '-->' not in lines[i]:
                text_chunk.append(lines[i].strip())
                i += 1
            if text_chunk:
                processed_text.append(' '.join(text_chunk))
        else:
            i += 1

    return ' '.join(processed_text)


def process_ass_content(content: str) -> str:
    """Parse ASS subtitle content and return clean transcript text."""
    processed_text = []
    in_events = False

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.lower() == '[events]':
            in_events = True
            continue
        if in_events and stripped.startswith('['):
            break
        if not in_events or not stripped.lower().startswith('dialogue:'):
            continue

        fields = stripped.split(',', 9)
        if len(fields) < 10:
            continue
        text = fields[-1]
        text = re.sub(r'\{[^}]*\}', '', text)
        text = text.replace(r'\N', ' ').replace(r'\n', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        if text:
            processed_text.append(text)

    return ' '.join(processed_text)


def process_file(file_path: Path) -> str:
    """Process a single subtitle file, auto-detecting its format."""
    encodings = ['utf-8', 'gbk', 'latin-1']
    content = None
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as file:
                content = file.read()
            break
        except UnicodeDecodeError:
            continue
    
    if content is None:
        print(f"  [WARN] Could not read file: {file_path}")
        return ""

    suffix = file_path.suffix.lower()
    
    if suffix in HTML_SUFFIXES:
        return html_to_text(content)
    if suffix == '.ass':
        return process_ass_content(content)
    if suffix == '.vtt' or content.strip().startswith('WEBVTT'):
        return process_vtt_content(content)
    return process_srt_content(content)


def natural_sort_key(s: str) -> list:
    """Key function for natural (human-friendly) sort order."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(s))]


def collect_input_files(path: Path, include_html: bool) -> list[Path]:
    suffixes = SUBTITLE_SUFFIXES | (HTML_SUFFIXES if include_html else set())
    return sorted(
        (child for child in path.iterdir() if child.is_file() and child.suffix.lower() in suffixes),
        key=natural_sort_key,
    )


def write_markdown(out_file: Path, title: str, content: str) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(f"# {title}\n\n{content}\n", encoding='utf-8')
    print(f"[OK] Generated: {out_file}")


def reserve_output_path(input_file: Path, out_dir: Path, used_names: set[str]) -> Path:
    out_path = out_dir / f"{input_file.stem}.md"
    if out_path.name in used_names:
        suffix = input_file.suffix.lower().lstrip('.') or 'subtitle'
        out_path = out_dir / f"{input_file.stem}_{suffix}.md"
        counter = 2
        while out_path.name in used_names:
            out_path = out_dir / f"{input_file.stem}_{suffix}_{counter}.md"
            counter += 1
    used_names.add(out_path.name)
    return out_path


def convert_subtitle_file(input_file: str, output_file: str | None = None) -> int:
    """Convert a single subtitle file to Markdown."""
    in_path = Path(input_file)
    if not in_path.exists() or not in_path.is_file():
        print(f"[ERROR] File not found: {input_file}")
        return 1

    if in_path.suffix.lower() not in SUBTITLE_SUFFIXES | HTML_SUFFIXES:
        print(f"[ERROR] Unsupported subtitle format: {in_path.suffix}")
        return 1

    content = process_file(in_path)
    if not content:
        print("[ERROR] No content extracted")
        return 1

    out_path = Path(output_file) if output_file else in_path.with_suffix('.md')
    write_markdown(out_path, in_path.stem, content)
    print(f"OUTPUT: {out_path.resolve()}")
    return 0


def convert_flat_directory(root_path: Path, out_path: Path, include_html: bool) -> int:
    """Convert subtitle files directly under a directory."""
    files = collect_input_files(root_path, include_html)
    if not files:
        print(f"[ERROR] No subtitle files found in: {root_path}")
        return 1

    generated = 0
    used_outputs: set[str] = set()
    for file_path in files:
        content = process_file(file_path)
        if not content:
            print(f"  [WARN] No content extracted: {file_path.name}")
            continue
        write_markdown(reserve_output_path(file_path, out_path, used_outputs), file_path.stem, content)
        generated += 1

    return 0 if generated else 1


def convert_subtitles(input_dir: str, output_dir: str | None = None, include_html: bool = False) -> int:
    """Convert subtitle files in a course directory to Markdown."""
    root_path = Path(input_dir)
    
    if not root_path.exists():
        print(f"[ERROR] Directory not found: {input_dir}")
        return 1
    if not root_path.is_dir():
        return convert_subtitle_file(input_dir, output_dir)

    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = root_path / "0-srt"
    
    out_path.mkdir(parents=True, exist_ok=True)

    if collect_input_files(root_path, include_html):
        rc = convert_flat_directory(root_path, out_path, include_html)
        if rc == 0:
            print(f"[OK] Done. Output: {out_path}")
        return rc

    output_dir_resolved = out_path.resolve()
    chapter_dirs = [
        d for d in root_path.iterdir()
        if d.is_dir() and d.name != '0-srt' and d.resolve() != output_dir_resolved
    ]
    chapter_dirs.sort(key=natural_sort_key)

    if not chapter_dirs:
        print(f"[ERROR] No subtitle files or chapter subdirectories found in: {input_dir}")
        return 1

    generated = 0
    for chapter_dir in chapter_dirs:
        chapter_name = chapter_dir.name
        print(f"[INFO] Processing chapter: {chapter_name}")

        markdown_content = f"# {chapter_name}\n\n"
        all_files = collect_input_files(chapter_dir, include_html)

        if not all_files:
            print(f"  [SKIP] No subtitle files")
            continue

        for file_path in all_files:
            file_name = file_path.stem
            file_type = file_path.suffix.lower()
            print(f"  [INFO] Processing: {file_name} ({file_type})")

            processed_content = process_file(file_path)

            if not processed_content:
                print(f"    [WARN] No content extracted")
                continue

            markdown_content += f"## {file_name}\n\n{processed_content}\n\n"

        markdown_path = out_path / f"{chapter_name}.md"
        with open(markdown_path, 'w', encoding='utf-8') as md_file:
            md_file.write(markdown_content)

        print(f"  [OK] Generated: {markdown_path.name}")
        generated += 1

    print(f"[OK] Done. Output: {out_path}")
    return 0 if generated else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Convert subtitle files (SRT/VTT/ASS) to Markdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python3 subtitle_to_md.py lecture.srt
  python3 subtitle_to_md.py /path/to/course
  python3 subtitle_to_md.py ./my-course -o ./output
  python3 subtitle_to_md.py ./course --include-html
        '''
    )
    
    parser.add_argument('input', help='subtitle file or course directory path')
    parser.add_argument('-o', '--output', help='output Markdown file for file input, or output directory for directory input')
    parser.add_argument('--include-html', action='store_true', 
                        help='also include HTML files')
    
    args = parser.parse_args()
    
    return convert_subtitles(args.input, args.output, args.include_html)


if __name__ == "__main__":
    exit(main())
