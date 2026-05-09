#!/usr/bin/env python3
"""Subtitle to Markdown converter.

Converts SRT/VTT subtitle files (single file or course directory) to Markdown.
Strips timestamps and outputs clean transcript text.
"""

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path


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
    
    if suffix == '.html' or suffix == '.htm':
        return html_to_text(content)
    elif suffix == '.vtt' or content.strip().startswith('WEBVTT'):
        return process_vtt_content(content)
    else:
        return process_srt_content(content)


def natural_sort_key(s: str) -> list:
    """Key function for natural (human-friendly) sort order."""
    return [int(text) if text.isdigit() else text.lower()
            for text in re.split(r'(\d+)', str(s))]


def convert_subtitles(input_dir: str, output_dir: str | None = None, include_html: bool = False) -> None:
    """Convert subtitle files in a course directory to Markdown."""
    root_path = Path(input_dir)
    
    if not root_path.exists():
        print(f"[ERROR] Directory not found: {input_dir}")
        return

    if output_dir:
        out_path = Path(output_dir)
    else:
        out_path = root_path / "0-srt"
    
    out_path.mkdir(exist_ok=True)

    chapter_dirs = [d for d in root_path.iterdir() if d.is_dir() and d.name != '0-srt']
    chapter_dirs.sort(key=natural_sort_key)

    if not chapter_dirs:
        print(f"[ERROR] No chapter subdirectories found in: {input_dir}")
        return

    for chapter_dir in chapter_dirs:
        chapter_name = chapter_dir.name
        print(f"[INFO] Processing chapter: {chapter_name}")

        markdown_content = f"# {chapter_name}\n\n"

        srt_files = list(chapter_dir.glob('*.srt'))
        vtt_files = list(chapter_dir.glob('*.vtt'))
        all_files = srt_files + vtt_files
        
        if include_html:
            html_files = list(chapter_dir.glob('*.html')) + list(chapter_dir.glob('*.htm'))
            all_files.extend(html_files)
        
        all_files.sort(key=natural_sort_key)

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

    print(f"[OK] Done. Output: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Convert subtitle files (SRT/VTT/ASS) to Markdown',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python subtitle_to_md.py /path/to/course
  python subtitle_to_md.py ./my-course -o ./output
  python subtitle_to_md.py ./course --include-html
        '''
    )
    
    parser.add_argument('input', help='course directory path')
    parser.add_argument('-o', '--output', help='output directory (default: <input>/0-srt)')
    parser.add_argument('--include-html', action='store_true', 
                        help='also include HTML files')
    
    args = parser.parse_args()
    
    convert_subtitles(args.input, args.output, args.include_html)
    return 0


if __name__ == "__main__":
    exit(main())
