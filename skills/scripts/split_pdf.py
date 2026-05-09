#!/usr/bin/env python3
"""PDF splitter.

Splits a PDF into multiple files by bookmark, chapter, or section structure.
Requires PyPDF2.
"""

import argparse
from pathlib import Path
from PyPDF2 import PdfReader, PdfWriter


def create_valid_filename(title: str) -> str:
    """Create a valid filename by stripping characters that are illegal on most filesystems."""
    invalid_chars = '<>:"/\\|?*'
    filename = ''.join(c if c not in invalid_chars else '_' for c in title)
    return filename.strip()


# ============= Bookmark mode =============

def get_bookmarks_with_pages(pdf_reader: PdfReader) -> list[tuple[str, int, int]]:
    """Return a list of (title, start_page, end_page) tuples from PDF bookmarks."""
    outlines = pdf_reader.outline
    bookmarks = []

    if not outlines:
        return []

    valid_bookmarks = []
    for i in range(len(outlines)):
        try:
            if not isinstance(outlines[i], dict) or '/Page' not in str(outlines[i]):
                continue
            current_title = outlines[i].title if hasattr(outlines[i], 'title') else f"Chapter {i+1}"
            try:
                current_page = pdf_reader.get_destination_page_number(outlines[i])
                valid_bookmarks.append((current_title, current_page))
            except Exception:
                continue
        except Exception:
            continue

    valid_bookmarks.sort(key=lambda x: x[1])

    for i, (title, start_page) in enumerate(valid_bookmarks):
        if i < len(valid_bookmarks) - 1:
            end_page = valid_bookmarks[i+1][1] - 1
        else:
            end_page = len(pdf_reader.pages) - 1
        bookmarks.append((title, start_page, end_page))

    return bookmarks


def get_nested_bookmarks(pdf_reader: PdfReader, start_page: int, end_page: int) -> list[dict]:
    """Return bookmarks that fall within the given page range."""
    def process_outline(outline, parent_list=None):
        if parent_list is None:
            parent_list = []
        if isinstance(outline, list):
            for item in outline:
                process_outline(item, parent_list)
        elif isinstance(outline, dict) and '/Page' in str(outline):
            try:
                page_num = pdf_reader.get_destination_page_number(outline)
                if start_page <= page_num <= end_page:
                    new_page_num = page_num - start_page
                    title = outline.title if hasattr(outline, 'title') else "Untitled"
                    parent_list.append({'title': title, 'page': new_page_num, 'children': []})
            except Exception:
                pass

    result = []
    process_outline(pdf_reader.outline, result)
    return result


def add_bookmarks_to_pdf(pdf_writer: PdfWriter, bookmarks: list[dict], parent=None) -> None:
    """Add bookmark entries to a PDF writer."""
    for bookmark in bookmarks:
        current = pdf_writer.add_outline_item(bookmark['title'], bookmark['page'], parent)
        if bookmark['children']:
            add_bookmarks_to_pdf(pdf_writer, bookmark['children'], current)


# ============= Chapter mode =============

def get_bookmark_level(bookmark: object) -> int:
    """Determine the hierarchy level of a bookmark (1 = chapter, 2 = section, 0 = other)."""
    if not isinstance(bookmark, dict) or '/Page' not in str(bookmark):
        return 0

    title = bookmark.title if hasattr(bookmark, 'title') else ""
    title_lower = title.lower()

    if any(x in title_lower for x in ["章", "chapter", "part"]):
        return 1
    elif any(x in title_lower for x in ["节", "section", "小节"]):
        return 2

    if title.strip() and title[0].isdigit():
        parts = title.split('.')
        if len(parts) == 2:
            return 1
        elif len(parts) >= 3:
            return 2

    return 0


def get_bookmarks_hierarchy(pdf_reader: PdfReader) -> list[dict[str, object]]:
    """Build a chapter/section hierarchy from the PDF's bookmark outline."""
    outlines = pdf_reader.outline
    if not outlines:
        return []

    bookmarks_info = []
    for i, bookmark in enumerate(outlines):
        level = get_bookmark_level(bookmark)
        if level > 0:
            try:
                page_num = pdf_reader.get_destination_page_number(bookmark)
                title = bookmark.title if hasattr(bookmark, 'title') else f"Bookmark {i+1}"
                bookmarks_info.append({'title': title, 'page': page_num, 'level': level})
            except Exception:
                continue

    chapters = []
    current_chapter = None

    for bookmark in bookmarks_info:
        if bookmark['level'] == 1:
            if current_chapter is not None:
                current_chapter['end_page'] = bookmark['page'] - 1
            current_chapter = {
                'title': bookmark['title'],
                'start_page': bookmark['page'],
                'end_page': len(pdf_reader.pages) - 1,
                'sections': []
            }
            chapters.append(current_chapter)
        elif bookmark['level'] == 2 and current_chapter is not None:
            section = {
                'title': bookmark['title'],
                'start_page': bookmark['page'],
                'end_page': len(pdf_reader.pages) - 1
            }
            if current_chapter['sections']:
                current_chapter['sections'][-1]['end_page'] = bookmark['page'] - 1
            current_chapter['sections'].append(section)

    if chapters and chapters[-1]['sections']:
        chapters[-1]['sections'][-1]['end_page'] = chapters[-1]['end_page']

    return chapters


# ============= Split function =============

def split_pdf(pdf_path: str, mode: str = 'bookmark', prefix: str = '', output_dir: str | None = None) -> None:
    """Split a PDF file into separate files by bookmark, chapter, or section."""
    if not Path(pdf_path).exists():
        print(f"[ERROR] File not found: {pdf_path}")
        return

    input_dir = Path(pdf_path).parent
    pdf_name = Path(pdf_path).stem

    if output_dir:
        out_dir = Path(output_dir)
    else:
        suffix = '_split' if mode == 'bookmark' else '_chapters'
        out_dir = input_dir / f"{pdf_name}{suffix}"

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Processing: {pdf_path}")
    print(f"[INFO] Mode: {mode}")
    
    pdf_reader = PdfReader(pdf_path)

    if mode == 'bookmark':
        bookmarks = get_bookmarks_with_pages(pdf_reader)
        if not bookmarks:
            print("[ERROR] No valid bookmarks found")
            return

        print(f"[INFO] Found {len(bookmarks)} bookmarks")

        for i, (title, start_page, end_page) in enumerate(bookmarks, 1):
            try:
                pdf_writer = PdfWriter()
                for page_num in range(start_page, end_page + 1):
                    if page_num < len(pdf_reader.pages):
                        pdf_writer.add_page(pdf_reader.pages[page_num])

                nested = get_nested_bookmarks(pdf_reader, start_page, end_page)
                add_bookmarks_to_pdf(pdf_writer, nested)
                if not nested:
                    pdf_writer.add_outline_item(title, 0)

                safe_title = create_valid_filename(title)
                if prefix:
                    filename = f"{prefix}_{i:02d}-{safe_title}.pdf"
                else:
                    filename = f"{i:02d}-{safe_title}.pdf"
                
                out_path = out_dir / filename
                with open(out_path, 'wb') as f:
                    pdf_writer.write(f)

                print(f"  [OK] {filename}")

            except Exception as e:
                print(f"  [FAIL] {title}: {e}")

    else:  # chapter or section
        chapters = get_bookmarks_hierarchy(pdf_reader)
        if not chapters:
            print("[ERROR] No valid chapter structure found")
            return

        print(f"[INFO] Found {len(chapters)} chapters")

        if mode == 'chapter':
            for i, chapter in enumerate(chapters, 1):
                try:
                    pdf_writer = PdfWriter()
                    for page_num in range(chapter['start_page'], chapter['end_page'] + 1):
                        if page_num < len(pdf_reader.pages):
                            pdf_writer.add_page(pdf_reader.pages[page_num])

                    safe_title = create_valid_filename(chapter['title'])
                    filename = f"{i:02d}-{safe_title}.pdf"
                    out_path = out_dir / filename

                    with open(out_path, 'wb') as f:
                        pdf_writer.write(f)

                    print(f"  [OK] {filename}")

                except Exception as e:
                    print(f"  [FAIL] {chapter['title']}: {e}")

        else:  # section
            for i, chapter in enumerate(chapters, 1):
                if not chapter['sections']:
                    try:
                        pdf_writer = PdfWriter()
                        for page_num in range(chapter['start_page'], chapter['end_page'] + 1):
                            if page_num < len(pdf_reader.pages):
                                pdf_writer.add_page(pdf_reader.pages[page_num])

                        safe_title = create_valid_filename(chapter['title'])
                        filename = f"{i:02d}-{safe_title}.pdf"
                        out_path = out_dir / filename

                        with open(out_path, 'wb') as f:
                            pdf_writer.write(f)

                        print(f"  [OK] {filename}")
                    except Exception as e:
                        print(f"  [FAIL] {chapter['title']}: {e}")
                else:
                    for j, section in enumerate(chapter['sections'], 1):
                        try:
                            pdf_writer = PdfWriter()
                            for page_num in range(section['start_page'], section['end_page'] + 1):
                                if page_num < len(pdf_reader.pages):
                                    pdf_writer.add_page(pdf_reader.pages[page_num])

                            safe_title = create_valid_filename(section['title'])
                            filename = f"{i:02d}-{j:02d}-{safe_title}.pdf"
                            out_path = out_dir / filename

                            with open(out_path, 'wb') as f:
                                pdf_writer.write(f)

                            print(f"  [OK] {filename}")

                        except Exception as e:
                            print(f"  [FAIL] {section['title']}: {e}")

    print(f"[OK] Done. Output: {out_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Split a PDF file by bookmarks, chapters, or sections',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Split modes:
  bookmark  Split by top-level bookmarks (default)
  chapter   Split by chapter (inferred from bookmark keywords)
  section   Split by section (inferred down to sub-section level)

Examples:
  python split_pdf.py book.pdf
  python split_pdf.py book.pdf --mode chapter
  python split_pdf.py book.pdf -m section -o ./output
        '''
    )

    parser.add_argument('input', help='PDF file path')
    parser.add_argument('-m', '--mode', choices=['bookmark', 'chapter', 'section'],
                        default='bookmark', help='split mode (default: bookmark)')
    parser.add_argument('-o', '--output', help='output directory')
    parser.add_argument('-p', '--prefix', default='', help='output filename prefix')
    
    args = parser.parse_args()
    
    split_pdf(args.input, args.mode, args.prefix, args.output)
    return 0


if __name__ == "__main__":
    exit(main())
