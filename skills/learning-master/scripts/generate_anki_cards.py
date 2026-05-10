import argparse
import os
import re
import sys

import markdown

# Constants
ANKI_FILE_SUFFIX = '-anki.txt'
QA_BLOCK_PATTERN = r'\*\*Q\*\*:\s*(.*?)\s*\n\*\*A\*\*:\s*(.*)'
MARKDOWN_EXTENSIONS = ['extra', 'nl2br']


def convert_tables_to_bullets(text: str) -> str:
    """Convert Markdown tables to bullet-point lists for better mobile readability.

    A table like:
        | 列A | 列B |
        |-----|-----|
        | 值1 | 值2 |

    becomes:
        - **列A**: 值1, **列B**: 值2

    Args:
        text: The raw markdown text to process.

    Returns:
        The processed text with tables replaced by bullet-point lists.
    """
    lines = text.split('\n')
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect table header: contains '|' and is followed by a separator row (---|--- pattern)
        if '|' in line and i + 1 < len(lines) and re.match(r'^\s*\|[\s\-:|]+\|\s*$', lines[i + 1]):
            headers = [cell.strip() for cell in line.strip().strip('|').split('|')]
            i += 2  # skip header row and separator row
            # Collect data rows
            while i < len(lines) and '|' in lines[i] and not re.match(r'^\s*\|[\s\-:|]+\|\s*$', lines[i]):
                cells = [cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                pairs: list[str] = []
                for j, header in enumerate(headers):
                    cell_val = cells[j] if j < len(cells) else ''
                    if header and cell_val:
                        pairs.append(f'**{header}**: {cell_val}')
                    elif cell_val:
                        pairs.append(cell_val)
                if pairs:
                    result.append('- ' + ', '.join(pairs))
                i += 1
        else:
            result.append(line)
            i += 1
    return '\n'.join(result)


def preprocess_markdown(text: str) -> str:
    """Fix common markdown formatting issues that prevent strict parsers from rendering correctly.

    1. Ensure a blank line exists before a list starts (if preceded by text).
    2. Fix list indentation for nesting (strict markdown requires 4 spaces).

    Args:
        text: The raw markdown text to process.

    Returns:
        The processed markdown text with fixed formatting.
    """
    # Fix: Text immediately followed by list items (without blank line)
    # Pattern: Non-newline char, newline, optional space, bullet/number, space
    text = re.sub(r'([^\n])\n(\s*[-*]\s)', r'\1\n\n\2', text)
    text = re.sub(r'([^\n])\n(\s*\d+\.\s)', r'\1\n\n\2', text)

    # Fix: List indentation. Promote 2-3 space indentation to 4 spaces to ensure nesting works.
    # Note: (?m) makes ^ match start of line.
    text = re.sub(r'(?m)^\s{2,3}([-*])', r'    \1', text)

    return text


def normalize_tsv_field(html_text: str) -> str:
    """Normalize rendered HTML so it can be stored in a single TSV field."""
    code_blocks: list[str] = []

    def stash_code_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(0).replace('\n', '<br>'))
        return f"@@CODE_BLOCK_{len(code_blocks) - 1}@@"

    text = re.sub(r'<pre><code.*?</code></pre>', stash_code_block, html_text, flags=re.DOTALL)
    text = (
        text
        .replace('\r\n', '\n')
        .replace('\r', '\n')
        .replace('\n', ' ')
    )

    for index, block in enumerate(code_blocks):
        text = text.replace(f"@@CODE_BLOCK_{index}@@", block)

    return (
        text
        .replace('\t', '    ')
        .strip()
    )


def process_single_file(filepath: str, output_dir: str | None = None) -> None:
    """Process a single markdown file and generate an Anki import file.

    Reads a markdown file, extracts Q&A pairs matching the specific pattern, converts them
    to HTML, and saves them as a tab-separated text file suitable for Anki import.
    Output is written to `output_dir` if specified, otherwise to an `anki-export/`
    subdirectory next to the source file.

    Args:
        filepath: The absolute or relative path to the markdown file.
        output_dir: Directory to write the output file. Defaults to an `anki-export/`
                    subdirectory in the same directory as the source file.
    """
    if not filepath.endswith(".md"):
        print(f"Skipping non-markdown file: {filepath}")
        return

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        return

    # Assuming cards follow the format:
    # ---
    # **Q**: Question text
    # **A**: Answer text
    
    chunks = content.split('\n---')
    cards: list[str] = []

    for chunk in chunks:
        # Relaxed regex to catch Question/Answer blocks
        match = re.search(QA_BLOCK_PATTERN, chunk, re.DOTALL)

        if match:
            question_md = match.group(1).strip()
            answer_md = match.group(2).strip()

            # Convert tables to bullet points, then preprocess
            question_md = convert_tables_to_bullets(question_md)
            answer_md = convert_tables_to_bullets(answer_md)
            question_md = preprocess_markdown(question_md)
            answer_md = preprocess_markdown(answer_md)

            # Convert
            q_html = markdown.markdown(question_md, extensions=MARKDOWN_EXTENSIONS)
            a_html = markdown.markdown(answer_md, extensions=MARKDOWN_EXTENSIONS)

            q_one_line = normalize_tsv_field(q_html)
            a_one_line = normalize_tsv_field(a_html)

            cards.append(f"{q_one_line}\t{a_one_line}")

    if cards:
        # Determine output directory: explicit arg > anki-export/ sibling of source file
        src_dir = os.path.dirname(os.path.abspath(filepath))
        dest_dir = output_dir if output_dir else os.path.join(src_dir, 'anki-export')
        os.makedirs(dest_dir, exist_ok=True)

        basename = os.path.splitext(os.path.basename(filepath))[0] + ANKI_FILE_SUFFIX
        output_path = os.path.join(dest_dir, basename)
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(cards))
            print(f"Generated {len(cards)} cards: {output_path}")
        except Exception as e:
            print(f"Error writing to {output_path}: {e}")
    else:
        print(f"No cards found in: {filepath}")


def main() -> None:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Convert Markdown files with Q&A format to Anki import files."
    )
    parser.add_argument(
        "path",
        help="Path to a Markdown file or a directory containing Markdown files."
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write output TSV files. Defaults to anki-export/ next to each source file."
    )

    args = parser.parse_args()
    target_path: str = args.path
    output_dir: str | None = args.output_dir

    if os.path.isfile(target_path):
        process_single_file(target_path, output_dir)
    elif os.path.isdir(target_path):
        # Process all .md files in the directory
        files = [
            os.path.join(target_path, f)
            for f in sorted(os.listdir(target_path))
            if f.endswith(".md")
        ]
        if not files:
            print(f"No Markdown files found in directory: {target_path}")
        # When processing a directory, default output goes to anki-export/ inside that dir
        effective_output_dir = output_dir if output_dir else os.path.join(target_path, 'anki-export')
        for f in files:
            process_single_file(f, effective_output_dir)
    else:
        print(f"Error: Path not found: {target_path}")
        sys.exit(1)


if __name__ == "__main__":
    main()
