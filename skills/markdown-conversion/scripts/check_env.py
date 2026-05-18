#!/usr/bin/env python3
"""Environment check for the markdown-conversion skill.

Verifies that all required and optional dependencies are available.
"""

import importlib
import json
import os
import shutil
import sys
from pathlib import Path


def check_python_version() -> bool:
    print(f"Checking Python version... {sys.version.split()[0]}")
    if sys.version_info < (3, 8):
        print("[ERROR] Python 3.8+ is required.")
        return False
    print("[OK] Python version OK")
    return True


def check_python_package(package_name: str, import_name: str | None = None) -> bool:
    import_name = import_name or package_name
    print(f"Checking python package: {package_name}...", end=" ")
    try:
        importlib.import_module(import_name)
        print("[OK] Installed")
        return True
    except ImportError:
        print(f"[MISSING] Missing. Install with: pip install {package_name}")
        return False


def check_optional_python_package(package_name: str, import_name: str | None = None) -> None:
    import_name = import_name or package_name
    print(f"Checking optional python package: {package_name}...", end=" ")
    try:
        importlib.import_module(import_name)
        print("[OK] Installed")
    except ImportError:
        print(f"[WARN] Missing. Install with: pip install {package_name}")


def check_command(command: str, install_hint: str) -> bool:
    print(f"Checking command: {command}...", end=" ")
    path = shutil.which(command)
    if path:
        print(f"[OK] Found: {path}")
        return True
    print(f"[MISSING] Missing. {install_hint}")
    return False


def check_optional_command(command: str, install_hint: str) -> None:
    print(f"Checking optional command: {command}...", end=" ")
    path = shutil.which(command)
    if path:
        print(f"[OK] Found: {path}")
    else:
        print(f"[WARN] Missing. {install_hint}")


def check_mineru_token() -> None:
    print("Checking MinerU API Token...", end=" ")
    token = os.getenv("MINERU_API_TOKEN")
    config_path = Path(__file__).parent.parent / "resources" / "config.json"

    if not token and config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            token = config.get("mineru_api_token")
        except (OSError, json.JSONDecodeError):
            pass

    if token:
        print("[OK] Found")
    else:
        print("[WARN] Not found (Required only for MinerU conversion)")


def command_available(command: str) -> bool:
    return shutil.which(command) is not None


def package_available(import_name: str) -> bool:
    try:
        importlib.import_module(import_name)
        return True
    except ImportError:
        return False


def print_capability_status() -> None:
    fitz_ok = package_available("fitz")
    requests_ok = package_available("requests")
    mammoth_ok = package_available("mammoth")
    bs4_ok = package_available("bs4")
    markdownify_ok = package_available("markdownify")
    ebooklib_ok = package_available("ebooklib")
    nbconvert_ok = package_available("nbconvert")
    openpyxl_ok = package_available("openpyxl")
    pptx_ok = package_available("pptx")
    curl_cffi_ok = package_available("curl_cffi")
    trafilatura_ok = package_available("trafilatura")
    pandoc_ok = command_available("pandoc")
    token_ok = bool(os.getenv("MINERU_API_TOKEN"))

    config_path = Path(__file__).parent.parent / "resources" / "config.json"
    if not token_ok and config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            token_ok = bool(config.get("mineru_api_token"))
        except (OSError, json.JSONDecodeError):
            token_ok = False

    print("-" * 20)
    print("Capability Status")
    print("-" * 20)
    print(f"PDF (local): {'READY' if fitz_ok else 'MISSING PyMuPDF'}")
    print(f"PDF (MinerU): {'READY' if requests_ok and token_ok else 'MISSING token or requests'}")
    print(f"Word .docx (native): {'READY' if mammoth_ok else 'MISSING mammoth'}")
    print(f"HTML (native): {'READY' if bs4_ok and markdownify_ok else 'MISSING beautifulsoup4 / markdownify'}")
    print(f"EPUB (native): {'READY' if ebooklib_ok and markdownify_ok else 'MISSING ebooklib / markdownify'}")
    print(f"Jupyter .ipynb: {'READY' if nbconvert_ok else 'MISSING nbconvert'}")
    print(f"Document (Pandoc fallback): {'READY' if pandoc_ok else 'MISSING pandoc (only for .doc/.odt/.rtf/.tex/.rst/.org/.typ)'}")
    print(f"Excel: {'READY' if openpyxl_ok else 'MISSING openpyxl'}")
    print(f"PowerPoint: {'READY' if pptx_ok else 'MISSING python-pptx'}")
    web_status = 'READY' if requests_ok else 'MISSING requests'
    if curl_cffi_ok:
        web_status += ' + curl_cffi (TLS impersonation)'
    if trafilatura_ok:
        web_status += ' + trafilatura (main-content extraction)'
    elif requests_ok:
        web_status += ' + heuristic extraction (MISSING trafilatura)'
    print(f"Web: {web_status}")


def main() -> int:
    print("=" * 40)
    print("Markdown Conversion Skill Environment Check")
    print("=" * 40)

    all_good = True

    if not check_python_version():
        all_good = False

    print("-" * 20)

    required_packages = [
        ("PyMuPDF", "fitz"),
        ("requests", "requests"),
    ]
    for pkg, import_name in required_packages:
        if not check_python_package(pkg, import_name):
            all_good = False

    print("-" * 20)

    check_optional_command("pandoc", "Install with: brew install pandoc (Mac) or apt install pandoc (Linux)")

    print("-" * 20)

    # Optional Python packages — capability extensions
    check_optional_python_package("mammoth", "mammoth")          # doc_to_md .docx native
    check_optional_python_package("markdownify", "markdownify")  # doc_to_md .html / web
    check_optional_python_package("beautifulsoup4", "bs4")       # doc_to_md .html / web
    check_optional_python_package("ebooklib", "ebooklib")        # doc_to_md .epub
    check_optional_python_package("nbconvert", "nbconvert")      # doc_to_md .ipynb
    check_optional_python_package("openpyxl", "openpyxl")        # excel_to_md
    check_optional_python_package("python-pptx", "pptx")         # ppt_to_md
    check_optional_python_package("curl_cffi", "curl_cffi")      # web_to_md (TLS impersonation)
    check_optional_python_package("trafilatura", "trafilatura")  # web_to_md main-content extraction

    print("-" * 20)

    check_mineru_token()
    print_capability_status()

    print("=" * 40)
    if all_good:
        print("[DONE] Core environment is ready.")
        return 0

    print("[ERROR] Required dependencies are missing. Please install them and try again.")
    return 1


if __name__ == "__main__":
    exit(main())
