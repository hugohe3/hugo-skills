#!/usr/bin/env python3
"""MinerU API PDF to Markdown converter.

Uploads a PDF to the MinerU cloud API and downloads the resulting Markdown.
Requires a MinerU API token (https://mineru.net).
"""

import argparse
import os
import io
import json
import re
import sys
import time
import zipfile
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _image_filter import should_keep_image_bytes  # noqa: E402


# Matches Markdown image references like ![alt](src) or ![alt](src "title"),
# including multi-line alt text. Used to strip image refs when --no-images.
_IMAGE_REF_RE = re.compile(r'!\[[^\]]*\]\((?P<src>[^)]*)\)')


def strip_image_refs(markdown: str) -> str:
    """Remove all ![alt](src) image references from Markdown.

    Drops image-only lines entirely (avoids blank line scars) and removes
    inline image refs from text lines.
    """
    cleaned_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = _IMAGE_REF_RE.sub("", line)
        # If the original line was just image refs (now whitespace), drop it.
        if line.strip() and not stripped.strip():
            continue
        cleaned_lines.append(stripped)
    # Collapse 3+ blank lines into 2 to tidy up.
    text = "\n".join(cleaned_lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text


def image_ref_filename(src: str) -> str:
    """Return the basename from a Markdown image target."""
    src = src.strip()
    if src.startswith("<"):
        target = src[1:].split(">", 1)[0]
    else:
        target = src.split()[0].strip('"\'')
    return Path(target).name


def strip_image_refs_by_filenames(markdown: str, filenames: set[str]) -> str:
    """Remove Markdown image refs whose target basename is in filenames."""
    cleaned_lines: list[str] = []
    for line in markdown.splitlines():
        stripped = _IMAGE_REF_RE.sub(
            lambda match: "" if image_ref_filename(match.group("src")) in filenames else match.group(0),
            line,
        )
        if line.strip() and not stripped.strip():
            continue
        cleaned_lines.append(stripped)
    text = "\n".join(cleaned_lines)
    return re.sub(r'\n{3,}', '\n\n', text)


def load_config() -> dict[str, object]:
    """Load optional local configuration from resources/config.json."""
    config_path = Path(__file__).parent.parent / "resources" / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


class MinerUClient:
    """MinerU cloud API client for PDF extraction."""
    
    BASE_URL = "https://mineru.net/api/v4"
    
    def __init__(self, token: str | None = None):
        """
        Initialize the client.

        Token lookup order:
        1. The ``token`` argument passed directly.
        2. Environment variable ``MINERU_API_TOKEN``.
        3. ``mineru_api_token`` in resources/config.json.

        Args:
            token: MinerU API token. If omitted, read from config/env.
        """
        if token:
            self.token = token
        else:
            config = load_config()
            self.token = os.getenv("MINERU_API_TOKEN") or config.get("mineru_api_token")
        
        if not self.token:
            raise ValueError(
                "API token not found. Set MINERU_API_TOKEN or create "
                "skills/markdown-conversion/resources/config.json from config.example.json.\n"
                "Get a token at: https://mineru.net"
            )
        
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
    
    def extract_from_url(
        self,
        url: str,
        model_version: str = "vlm",
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: str | None = None,
        data_id: str | None = None
    ) -> str:
        """
        Submit a URL-based extraction task.

        Args:
            url: File URL to parse.
            model_version: "vlm" (more accurate) or "pipeline" (faster).
            is_ocr: Force OCR mode.
            enable_formula: Detect and render formulas.
            enable_table: Detect and render tables.
            language: Primary document language (default "ch").
            page_ranges: Page range string, e.g. "1-10" or "2,4-6".
            data_id: Optional business identifier for the task.

        Returns:
            task_id string.
        """
        endpoint = f"{self.BASE_URL}/extract/task"
        
        data = {
            "url": url,
            "model_version": model_version,
            "is_ocr": is_ocr,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
            "language": language
        }
        
        if page_ranges:
            data["page_ranges"] = page_ranges
        if data_id:
            data["data_id"] = data_id
        
        response = requests.post(endpoint, headers=self.headers, json=data)
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"Failed to create task: {result.get('msg', 'unknown error')}")
        
        task_id = result["data"]["task_id"]
        print(f"[OK] Task created: {task_id}")
        return task_id
    
    def upload_file(
        self,
        file_path: str,
        model_version: str = "vlm",
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: str | None = None,
        data_id: str | None = None
    ) -> str:
        """
        Upload a local file and create a batch extraction task.

        Args:
            file_path: Local PDF file path.
            model_version: "vlm" or "pipeline".
            is_ocr: Force OCR mode.
            enable_formula: Detect and render formulas.
            enable_table: Detect and render tables.
            language: Primary document language.
            page_ranges: Page range string, e.g. "1-10".
            data_id: Optional business identifier.

        Returns:
            batch_id string.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_name = file_path.name

        # 1. Request upload URL
        endpoint = f"{self.BASE_URL}/file-urls/batch"
        
        file_info = {"name": file_name}
        if data_id:
            file_info["data_id"] = data_id
        if page_ranges:
            file_info["page_ranges"] = page_ranges
        if is_ocr:
            file_info["is_ocr"] = is_ocr
        
        data = {
            "files": [file_info],
            "model_version": model_version,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
            "language": language
        }
        
        response = requests.post(endpoint, headers=self.headers, json=data)
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"Failed to get upload URL: {result.get('msg', 'unknown error')}")

        batch_id = result["data"]["batch_id"]
        upload_url = result["data"]["file_urls"][0]

        print(f"[OK] Upload URL obtained")

        # 2. Upload file
        with open(file_path, 'rb') as f:
            upload_response = requests.put(upload_url, data=f)
            if upload_response.status_code != 200:
                raise Exception(f"Upload failed: HTTP {upload_response.status_code}")

        print(f"[OK] Uploaded: {file_name}")
        print(f"[OK] Batch ID: {batch_id}")

        return batch_id
    
    def upload_files_batch(
        self,
        file_paths: list[str],
        model_version: str = "vlm",
        **kwargs
    ) -> str:
        """
        Upload multiple local files in a single batch.

        Args:
            file_paths: List of local file paths.
            model_version: "vlm" or "pipeline".

        Returns:
            batch_id string.
        """
        files_info = []
        for fp in file_paths:
            path = Path(fp)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path}")
            files_info.append({"name": path.name})
        
        # 1. Request upload URLs
        endpoint = f"{self.BASE_URL}/file-urls/batch"
        data = {
            "files": files_info,
            "model_version": model_version,
            **{k: v for k, v in kwargs.items() if v is not None}
        }
        
        response = requests.post(endpoint, headers=self.headers, json=data)
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"Failed to get upload URLs: {result.get('msg', 'unknown error')}")

        batch_id = result["data"]["batch_id"]
        upload_urls = result["data"]["file_urls"]

        print(f"[OK] Upload URLs obtained for {len(upload_urls)} files")

        # 2. Upload files
        for i, (fp, url) in enumerate(zip(file_paths, upload_urls)):
            with open(fp, 'rb') as f:
                upload_response = requests.put(url, data=f)
                if upload_response.status_code != 200:
                    raise Exception(f"Upload failed for: {fp}")
            print(f"  [{i+1}/{len(file_paths)}] Uploaded: {Path(fp).name}")

        print(f"[OK] Batch ID: {batch_id}")
        return batch_id
    
    def get_task_result(self, task_id: str) -> dict[str, object]:
        """
        Fetch the result for a single task.

        Args:
            task_id: Task identifier.

        Returns:
            Task result dict.
        """
        endpoint = f"{self.BASE_URL}/extract/task/{task_id}"
        response = requests.get(endpoint, headers=self.headers)
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"Failed to get task result: {result.get('msg', 'unknown error')}")
        
        return result["data"]
    
    def get_batch_result(self, batch_id: str) -> dict[str, object]:
        """
        Fetch the result for a batch task.

        Args:
            batch_id: Batch task identifier.

        Returns:
            Batch result dict.
        """
        endpoint = f"{self.BASE_URL}/extract-results/batch/{batch_id}"
        response = requests.get(endpoint, headers=self.headers)
        result = response.json()
        
        if result.get("code") != 0:
            raise Exception(f"Failed to get batch result: {result.get('msg', 'unknown error')}")
        
        return result["data"]
    
    def wait_for_task(
        self,
        task_id: str,
        poll_interval: int = 5,
        max_wait: int = 600
    ) -> dict[str, object]:
        """
        Wait for a single task to complete.
        
        Args:
            task_id: Task ID.
            poll_interval: Polling interval in seconds.
            max_wait: Maximum wait time in seconds.
        
        Returns:
            Task result dict.
        """
        start_time = time.time()
        
        while True:
            result = self.get_task_result(task_id)
            state = result.get("state")
            
            if state == "done":
                print(f"\n[OK] Task completed")
                return result
            elif state == "failed":
                raise Exception(f"Task failed: {result.get('err_msg', 'unknown error')}")
            elif state == "running":
                progress = result.get("extract_progress", {})
                extracted = progress.get("extracted_pages", 0)
                total = progress.get("total_pages", "?")
                print(f"\r  Parsing... {extracted}/{total} pages", end="", flush=True)
            else:
                print(f"\r  Status: {state}", end="", flush=True)
            
            if time.time() - start_time > max_wait:
                raise TimeoutError(f"Task timed out after {max_wait} seconds")
            
            time.sleep(poll_interval)
    
    def wait_for_batch(
        self,
        batch_id: str,
        poll_interval: int = 5,
        max_wait: int = 1200
    ) -> list[dict[str, object]]:
        """
        Wait for a batch task to complete.
        
        Args:
            batch_id: Batch task ID.
            poll_interval: Polling interval in seconds.
            max_wait: Maximum wait time in seconds.
        
        Returns:
            List of all task results.
        """
        start_time = time.time()
        
        while True:
            result = self.get_batch_result(batch_id)
            extract_results = result.get("extract_result", [])
            
            done_count = sum(1 for r in extract_results if r.get("state") == "done")
            failed_count = sum(1 for r in extract_results if r.get("state") == "failed")
            total_count = len(extract_results)
            
            print(f"\r  Progress: {done_count}/{total_count} done, {failed_count} failed", end="", flush=True)
            
            # Check if all tasks are finished
            all_done = all(
                r.get("state") in ["done", "failed"]
                for r in extract_results
            )
            
            if all_done:
                print(f"\n[OK] Batch task completed")
                return extract_results
            
            if time.time() - start_time > max_wait:
                raise TimeoutError(f"Batch task timed out after {max_wait} seconds")
            
            time.sleep(poll_interval)
    
    def download_and_extract(
        self,
        zip_url: str,
        output_dir: str,
        output_filename: str | None = None,
        extract_md: bool = True,
        no_images: bool = False,
        filter_images: bool = False,
    ) -> str:
        """
        Download and extract result archive.

        Args:
            zip_url: Result ZIP archive URL.
            output_dir: Output directory.
            output_filename: Output filename (without extension); defaults to the original name.
            extract_md: Whether to extract only Markdown files.
            no_images: When True, drop the images folder and strip image references from the Markdown.
            filter_images: When True, drop decorative / duplicate images from the synced images folder.

        Returns:
            Markdown file path or output directory.
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Download ZIP file
        response = requests.get(zip_url)
        if response.status_code != 200:
            raise Exception(f"Download failed: HTTP {response.status_code}")

        # Extract archive
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            # 1. Create mineru directory (for all raw extracted resources)
            mineru_base = output_path / "mineru"
            extract_dir = mineru_base / (output_filename or "unnamed")
            extract_dir.mkdir(parents=True, exist_ok=True)
            zf.extractall(extract_dir)
            print(f"[OK] Raw resources extracted to: {extract_dir}")

            # 2. Classify images before writing Markdown, so removed images can
            # also have their Markdown references stripped.
            source_images_dir = extract_dir / "images"
            kept_images: list[Path] = []
            dropped_image_names: set[str] = set()
            if not no_images and source_images_dir.exists() and source_images_dir.is_dir():
                seen_hashes: set[str] = set()
                for img_file in sorted(source_images_dir.glob("*")):
                    if not img_file.is_file():
                        continue
                    if filter_images:
                        try:
                            payload = img_file.read_bytes()
                        except OSError:
                            kept_images.append(img_file)
                            continue
                        if not should_keep_image_bytes(payload, seen_hashes=seen_hashes):
                            dropped_image_names.add(img_file.name)
                            continue
                    kept_images.append(img_file)

            # 3. Find MD files and copy to root directory (0-resources)
            md_files = [f for f in zf.namelist() if f.endswith('.md')]
            final_md_path = None
            if md_files:
                # Only process the first MD file found
                md_rel_path = md_files[0]
                source_md = extract_dir / md_rel_path

                # Use the PDF stem as the target filename
                dest_md_name = f"{output_filename}.md" if output_filename else Path(md_rel_path).name
                dest_md_path = output_path / dest_md_name

                if no_images:
                    md_text = source_md.read_text(encoding="utf-8", errors="replace")
                    md_text = strip_image_refs(md_text)
                    dest_md_path.write_text(md_text, encoding="utf-8")
                elif dropped_image_names:
                    md_text = source_md.read_text(encoding="utf-8", errors="replace")
                    md_text = strip_image_refs_by_filenames(md_text, dropped_image_names)
                    dest_md_path.write_text(md_text, encoding="utf-8")
                else:
                    dest_md_path.write_bytes(source_md.read_bytes())
                print(f"[OK] Markdown saved to: {dest_md_path}")
                final_md_path = str(dest_md_path)

            # 4. Sync images to root images/
            if no_images:
                print("[OK] Images skipped (--no-images)")
            elif kept_images:
                dest_images_dir = output_path / "images"
                dest_images_dir.mkdir(parents=True, exist_ok=True)

                import shutil
                for img_file in kept_images:
                    shutil.copy2(img_file, dest_images_dir / img_file.name)
                if filter_images:
                    print(
                        f"[OK] Images synced to: {dest_images_dir} "
                        f"({len(kept_images)} kept, {len(dropped_image_names)} filtered)"
                    )
                else:
                    print(f"[OK] Images synced to: {dest_images_dir}")
            elif filter_images and dropped_image_names:
                print(f"[OK] Images filtered: {len(dropped_image_names)} removed")

            # If no MD file found, return the extraction directory
            return final_md_path or str(extract_dir)

        return str(output_path)


def convert_local_file(
    file_path: str,
    output_dir: str | None = None,
    token: str | None = None,
    model_version: str = "vlm",
    no_images: bool = False,
    filter_images: bool = False,
    **kwargs
) -> str:
    """
    Convert a local PDF file to Markdown.
    
    Args:
        file_path: PDF file path.
        output_dir: Output directory (default: same directory as the file).
        token: API token.
        model_version: Model version.
    
    Returns:
        Markdown file path.
    """
    client = MinerUClient(token)
    
    file_path = Path(file_path)
    output_dir = output_dir or str(file_path.parent)
    
    print(f"[FILE] Processing: {file_path.name}")
    print(f"[DIR] Output directory: {output_dir}")
    print("-" * 40)
    
    # Upload file
    batch_id = client.upload_file(
        str(file_path),
        model_version=model_version,
        **kwargs
    )
    
    # Wait for completion
    print("[WAIT] Waiting for parsing to finish...")
    results = client.wait_for_batch(batch_id)
    
    # Download result, use PDF filename as output filename
    if results and results[0].get("state") == "done":
        zip_url = results[0]["full_zip_url"]
        output_filename = file_path.stem  # PDF filename without extension
        md_path = client.download_and_extract(
            zip_url,
            output_dir,
            output_filename=output_filename,
            no_images=no_images,
            filter_images=filter_images,
        )
        print("-" * 40)
        print(f"[DONE] Conversion complete: {md_path}")
        return md_path
    else:
        err_msg = results[0].get("err_msg", "unknown error") if results else "no result"
        raise Exception(f"Conversion failed: {err_msg}")


def convert_url(
    url: str,
    output_dir: str = "./output",
    token: str | None = None,
    model_version: str = "vlm",
    no_images: bool = False,
    filter_images: bool = False,
    **kwargs
) -> str:
    """
    Convert a URL file to Markdown.
    
    Args:
        url: File URL.
        output_dir: Output directory.
        token: API token.
        model_version: Model version.
    
    Returns:
        Markdown file path.
    """
    client = MinerUClient(token)
    
    print(f"[LINK] Processing URL: {url}")
    print(f"[DIR] Output directory: {output_dir}")
    print("-" * 40)
    
    # Create task
    task_id = client.extract_from_url(url, model_version=model_version, **kwargs)
    
    # Wait for completion
    print("[WAIT] Waiting for parsing to finish...")
    result = client.wait_for_task(task_id)
    
    # Download result
    if result.get("state") == "done":
        zip_url = result["full_zip_url"]
        md_path = client.download_and_extract(
            zip_url,
            output_dir,
            no_images=no_images,
            filter_images=filter_images,
        )
        print("-" * 40)
        print(f"[DONE] Conversion complete: {md_path}")
        return md_path
    else:
        raise Exception(f"Conversion failed: {result.get('err_msg', 'unknown error')}")


def convert_batch(
    file_paths: list[str],
    output_dir: str | None = None,
    token: str | None = None,
    model_version: str = "vlm",
    no_images: bool = False,
    filter_images: bool = False,
    **kwargs
) -> list[str]:
    """
    Batch-convert local files to Markdown.
    
    Args:
        file_paths: List of file paths.
        output_dir: Output directory (default: each file's own directory).
        token: API token.
        model_version: Model version.
    
    Returns:
        List of Markdown file paths.
    """
    client = MinerUClient(token)
    
    print(f"[FILE] Batch processing {len(file_paths)} files")
    if output_dir:
        print(f"[DIR] Output directory: {output_dir}")
    else:
        print(f"[DIR] Output directory: each file's own directory")
    print("-" * 40)
    
    # Batch upload
    batch_id = client.upload_files_batch(file_paths, model_version=model_version, **kwargs)
    
    # Wait for completion
    print("[WAIT] Waiting for parsing to finish...")
    results = client.wait_for_batch(batch_id)
    
    # Download results, use original filenames, output to respective directories
    md_paths = []
    for i, result in enumerate(results):
        if result.get("state") == "done":
            zip_url = result["full_zip_url"]
            # Get original file path
            original_path = Path(file_paths[i])
            # Output directory: specified or the file's own directory
            target_dir = output_dir or str(original_path.parent)
            # Use original filename
            output_filename = original_path.stem
            md_path = client.download_and_extract(
                zip_url,
                target_dir,
                output_filename=output_filename,
                no_images=no_images,
                filter_images=filter_images,
            )
            md_paths.append(md_path)
        else:
            print(f"[WARN] Skipping failed file: {result.get('file_name')}: {result.get('err_msg')}")
    
    print("-" * 40)
    print(f"[DONE] Batch conversion complete: {len(md_paths)}/{len(file_paths)} files")
    return md_paths


def main() -> int:
    parser = argparse.ArgumentParser(
        description='MinerU API PDF to Markdown converter',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Convert a local file
  python3 pdf_to_md_mineru.py document.pdf
  
  # Convert a URL file
  python3 pdf_to_md_mineru.py --url https://example.com/doc.pdf
  
  # Specify output directory
  python3 pdf_to_md_mineru.py document.pdf -o ./output
  
  # Batch convert
  python3 pdf_to_md_mineru.py file1.pdf file2.pdf file3.pdf
  
  # Use pipeline model (faster but slightly less accurate)
  python3 pdf_to_md_mineru.py document.pdf --model pipeline
  
  # Specify page range
  python3 pdf_to_md_mineru.py document.pdf --pages 1-10

Environment variables:
  MINERU_API_TOKEN: API Token (get one at https://mineru.net)
'''
    )
    
    parser.add_argument('files', nargs='*', help='PDF file paths to convert')
    parser.add_argument('--url', help='File URL to convert')
    parser.add_argument('-o', '--output', help='Output directory')
    parser.add_argument('--token', help='API Token (can also be set via env var)')
    parser.add_argument(
        '--model', 
        choices=['vlm', 'pipeline'], 
        default='vlm',
        help='Model version: vlm (more accurate) or pipeline (faster)'
    )
    parser.add_argument('--ocr', action='store_true', help='Enable OCR')
    parser.add_argument('--no-formula', action='store_true', help='Disable formula detection')
    parser.add_argument('--no-table', action='store_true', help='Disable table detection')
    parser.add_argument('--lang', default='ch', help='Document language (default: ch)')
    parser.add_argument('--pages', help='Page range, e.g. "1-10" or "2,4-6"')
    parser.add_argument(
        '--no-images',
        action='store_true',
        help='Skip image sync and strip image references from the Markdown',
    )
    parser.add_argument(
        '--filter-images',
        action='store_true',
        help='Filter decorative images after MinerU extraction',
    )
    parser.add_argument(
        '--raw',
        action='store_true',
        help='Accepted for parity with convert.py (MinerU cloud processing is not adjustable from here)',
    )
    
    args = parser.parse_args()

    if args.no_images and args.filter_images:
        print("Error: --no-images and --filter-images are mutually exclusive.")
        return 2
    
    # Build common parameters
    kwargs = {
        "is_ocr": args.ocr,
        "enable_formula": not args.no_formula,
        "enable_table": not args.no_table,
        "language": args.lang,
        "page_ranges": args.pages
    }
    
    if args.files:
        try:
            import fitz  # PyMuPDF
            for f in args.files:
                if Path(f).is_file() and Path(f).suffix.lower() == ".pdf":
                    try:
                        with fitz.open(f) as _doc:
                            n = len(_doc)
                        if n >= 200:
                            print(f"[HINT] {Path(f).name}: {n} pages — for very large PDFs, "
                                  f"consider splitting the source by chapter beforehand "
                                  f"(e.g. with pdftk / qpdf / PyPDF2) and converting each part individually.")
                    except Exception:
                        pass
        except ImportError:
            pass

    try:
        if args.url:
            # URL mode
            output_dir = args.output or "./output"
            convert_url(
                args.url,
                output_dir=output_dir,
                token=args.token,
                model_version=args.model,
                no_images=args.no_images,
                filter_images=args.filter_images,
                **kwargs
            )
        elif args.files:
            if len(args.files) == 1:
                # Single file mode
                convert_local_file(
                    args.files[0],
                    output_dir=args.output,
                    token=args.token,
                    model_version=args.model,
                    no_images=args.no_images,
                    filter_images=args.filter_images,
                    **kwargs
                )
            else:
                # Batch mode
                convert_batch(
                    args.files,
                    output_dir=args.output,  # Default None, output to each file's own directory
                    token=args.token,
                    model_version=args.model,
                    no_images=args.no_images,
                    filter_images=args.filter_images,
                    **kwargs
                )
        else:
            parser.print_help()
            return 1
            
    except Exception as e:
        error_msg = str(e)
        print(f"\n[ERROR] {error_msg}")
        
        if "user authenticate failed" in error_msg or "401" in error_msg:
            print("\n[TIP] Authentication failed. Please check:")
            print("1. Is the API Token valid? (https://mineru.net)")
            print("2. Is the token in MINERU_API_TOKEN or resources/config.json correct?")
            print("3. Or use local conversion mode (no token required):")
            print("   python3 convert.py <file>")
            
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
