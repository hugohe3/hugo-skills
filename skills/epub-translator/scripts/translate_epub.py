#!/usr/bin/env python3
"""Prepare and rebuild EPUB translations without calling any model API."""

from __future__ import annotations

import argparse
import json
import mimetypes
import posixpath
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


CONTAINER_PATH = "META-INF/container.xml"
XHTML_NAMESPACE = "http://www.w3.org/1999/xhtml"
SKIP_TAGS = {
    "script",
    "style",
    "code",
    "pre",
    "kbd",
    "samp",
    "var",
    "math",
    "svg",
}


@dataclass
class TextSlot:
    slot_id: str
    document: str
    path: list[int]
    attribute: str
    source: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare EPUB text chunks for agent translation and rebuild the EPUB."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Extract translatable text into JSONL chunks")
    prepare.add_argument("input", type=Path, help="Input .epub file")
    prepare.add_argument(
        "-w",
        "--work-dir",
        type=Path,
        required=True,
        help="Working directory for extracted EPUB and translation chunks",
    )
    prepare.add_argument(
        "--source-language",
        default="English",
        help="Source language label recorded in manifest.json",
    )
    prepare.add_argument(
        "--target-language",
        default="Simplified Chinese",
        help="Target language label recorded in manifest.json",
    )
    prepare.add_argument(
        "--chunk-chars",
        type=int,
        default=8000,
        help="Approximate maximum source characters per JSONL chunk",
    )
    prepare.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing work directory",
    )

    check = subparsers.add_parser("check", help="Check translation JSONL completeness")
    check.add_argument(
        "-w",
        "--work-dir",
        type=Path,
        required=True,
        help="Working directory created by prepare",
    )

    build = subparsers.add_parser("build", help="Apply translated JSONL and rebuild EPUB")
    build.add_argument(
        "-w",
        "--work-dir",
        type=Path,
        required=True,
        help="Working directory created by prepare",
    )
    build.add_argument("-o", "--output", type=Path, required=True, help="Output .epub file")
    build.add_argument(
        "--allow-missing",
        action="store_true",
        help="Keep source text when a translation is missing",
    )

    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def is_translatable_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[\W\d_]+", stripped, flags=re.UNICODE):
        return False
    if re.fullmatch(r"https?://\S+|[\w.-]+@[\w.-]+", stripped):
        return False
    return True


def unpack_epub(input_path: Path, source_dir: Path) -> None:
    with zipfile.ZipFile(input_path, "r") as epub:
        epub.extractall(source_dir)


def find_opf_path(source_dir: Path) -> Path:
    container_file = source_dir / CONTAINER_PATH
    if not container_file.exists():
        fail(f"missing {CONTAINER_PATH}")
    tree = ET.parse(container_file)
    root = tree.getroot()
    for element in root.iter():
        if local_name(element.tag) == "rootfile":
            full_path = element.attrib.get("full-path")
            if full_path:
                return source_dir / full_path
    fail("could not find OPF package path in container.xml")


def get_spine_documents(opf_path: Path) -> list[Path]:
    tree = ET.parse(opf_path)
    root = tree.getroot()
    manifest: dict[str, tuple[str, str]] = {}
    spine_ids: list[str] = []

    for element in root.iter():
        name = local_name(element.tag)
        if name == "item":
            item_id = element.attrib.get("id")
            href = element.attrib.get("href")
            media_type = element.attrib.get("media-type", "")
            if item_id and href:
                manifest[item_id] = (href, media_type)
        elif name == "itemref":
            itemref = element.attrib.get("idref")
            if itemref:
                spine_ids.append(itemref)

    documents: list[Path] = []
    base_dir = opf_path.parent
    for item_id in spine_ids:
        item = manifest.get(item_id)
        if not item:
            continue
        href, media_type = item
        if media_type not in {"application/xhtml+xml", "text/html"}:
            continue
        normalized = posixpath.normpath(href.split("#", 1)[0])
        documents.append(base_dir / normalized)
    return documents


def collect_text_slots(
    element: ET.Element,
    document: str,
    path: list[int],
    counters: dict[str, int],
    inherited_skip: bool = False,
) -> list[TextSlot]:
    tag_name = local_name(element.tag).lower()
    skip = inherited_skip or tag_name in SKIP_TAGS
    slots: list[TextSlot] = []

    if not skip and is_translatable_text(element.text or ""):
        slots.append(make_slot(document, path, "text", element.text or "", counters))

    for index, child in enumerate(list(element)):
        child_path = [*path, index]
        slots.extend(collect_text_slots(child, document, child_path, counters, skip))
        if not skip and is_translatable_text(child.tail or ""):
            slots.append(make_slot(document, child_path, "tail", child.tail or "", counters))

    return slots


def make_slot(
    document: str,
    path: list[int],
    attribute: str,
    source: str,
    counters: dict[str, int],
) -> TextSlot:
    counters["slot"] += 1
    slot_id = f"t{counters['slot']:06d}"
    return TextSlot(slot_id, document, path, attribute, source)


def batch_slots(slots: list[TextSlot], max_chars: int) -> Iterable[list[TextSlot]]:
    batch: list[TextSlot] = []
    current_chars = 0
    for slot in slots:
        slot_len = len(slot.source)
        if batch and current_chars + slot_len > max_chars:
            yield batch
            batch = []
            current_chars = 0
        batch.append(slot)
        current_chars += slot_len
    if batch:
        yield batch


def prepare_command(args: argparse.Namespace) -> None:
    if args.input.suffix.lower() != ".epub":
        fail("input file must have .epub extension")
    if not args.input.exists():
        fail(f"input file not found: {args.input}")
    if args.chunk_chars < 1000:
        fail("--chunk-chars must be at least 1000")
    if args.work_dir.exists():
        if not args.force:
            fail(f"work directory already exists: {args.work_dir}; pass --force to overwrite")
        shutil.rmtree(args.work_dir)

    source_dir = args.work_dir / "source"
    chunks_dir = args.work_dir / "chunks"
    translated_dir = args.work_dir / "translated"
    source_dir.mkdir(parents=True)
    chunks_dir.mkdir()
    translated_dir.mkdir()

    unpack_epub(args.input, source_dir)
    opf_path = find_opf_path(source_dir)
    documents = get_spine_documents(opf_path)
    if not documents:
        fail("no XHTML spine documents found")

    ET.register_namespace("", XHTML_NAMESPACE)
    counters = {"slot": 0}
    all_slots: list[TextSlot] = []
    document_records: list[str] = []

    for document_path in documents:
        relative = document_path.relative_to(source_dir).as_posix()
        document_records.append(relative)
        try:
            tree = ET.parse(document_path)
        except ET.ParseError as error:
            print(f"SKIP: {relative}: XML parse error: {error}", file=sys.stderr)
            continue
        all_slots.extend(collect_text_slots(tree.getroot(), relative, [], counters))

    manifest = {
        "input": str(args.input),
        "source_language": args.source_language,
        "target_language": args.target_language,
        "source_dir": "source",
        "chunks_dir": "chunks",
        "translated_dir": "translated",
        "documents": document_records,
        "slots": [
            {
                "id": slot.slot_id,
                "document": slot.document,
                "path": slot.path,
                "attribute": slot.attribute,
                "source": slot.source,
            }
            for slot in all_slots
        ],
    }
    write_json(args.work_dir / "manifest.json", manifest)

    chunk_count = 0
    for chunk_count, batch in enumerate(batch_slots(all_slots, args.chunk_chars), start=1):
        chunk_path = chunks_dir / f"chunk-{chunk_count:04d}.jsonl"
        with chunk_path.open("w", encoding="utf-8") as handle:
            for slot in batch:
                record = {
                    "id": slot.slot_id,
                    "source": slot.source,
                    "translation": "",
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"DONE: documents={len(document_records)} text_nodes={len(all_slots)} chunks={chunk_count}")
    print(f"WORK_DIR: {args.work_dir.resolve()}")
    print(f"NEXT: translate chunks/*.jsonl into translated/*.jsonl, then run build")


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_manifest(work_dir: Path) -> dict:
    manifest_path = work_dir / "manifest.json"
    if not manifest_path.exists():
        fail(f"missing manifest: {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def read_translations(work_dir: Path) -> dict[str, str]:
    translated_dir = work_dir / "translated"
    if not translated_dir.exists():
        fail(f"missing translated directory: {translated_dir}")

    translations: dict[str, str] = {}
    for path in sorted(translated_dir.glob("*.jsonl")):
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    fail(f"invalid JSON in {path}:{line_number}: {error}")
                slot_id = record.get("id")
                translation = record.get("translation")
                if isinstance(slot_id, str) and isinstance(translation, str) and translation:
                    translations[slot_id] = translation
    return translations


def check_command(args: argparse.Namespace) -> None:
    manifest = read_manifest(args.work_dir)
    slots = manifest.get("slots", [])
    translations = read_translations(args.work_dir)
    missing = [slot["id"] for slot in slots if slot["id"] not in translations]
    print(f"TOTAL: {len(slots)}")
    print(f"TRANSLATED: {len(translations)}")
    print(f"MISSING: {len(missing)}")
    if missing:
        print("FIRST_MISSING: " + ", ".join(missing[:20]))
        raise SystemExit(1)


def get_element(root: ET.Element, path: list[int]) -> ET.Element:
    element = root
    for index in path:
        children = list(element)
        if index >= len(children):
            fail(f"element path no longer exists: {path}")
        element = children[index]
    return element


def apply_translations_to_document(
    source_dir: Path,
    document: str,
    slots: list[dict],
    translations: dict[str, str],
    allow_missing: bool,
) -> int:
    document_path = source_dir / document
    tree = ET.parse(document_path)
    root = tree.getroot()
    applied = 0

    for slot in slots:
        slot_id = slot["id"]
        translation = translations.get(slot_id)
        if not translation:
            if allow_missing:
                continue
            fail(f"missing translation for {slot_id}")
        element = get_element(root, slot["path"])
        if slot["attribute"] == "text":
            element.text = translation
        else:
            element.tail = translation
        applied += 1

    tree.write(document_path, encoding="utf-8", xml_declaration=True)
    return applied


def write_epub(source_dir: Path, output_path: Path) -> None:
    mimetype_path = source_dir / "mimetype"
    temp_output = output_path.with_suffix(output_path.suffix + ".tmp")

    with zipfile.ZipFile(temp_output, "w") as epub:
        if mimetype_path.exists():
            epub.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

        for path in sorted(source_dir.rglob("*")):
            if path.is_dir() or path == mimetype_path:
                continue
            arcname = path.relative_to(source_dir).as_posix()
            guessed_type = mimetypes.guess_type(path.name)[0]
            compress_type = zipfile.ZIP_DEFLATED
            if guessed_type and guessed_type.startswith("image/"):
                compress_type = zipfile.ZIP_STORED
            epub.write(path, arcname, compress_type=compress_type)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(temp_output, output_path)


def build_command(args: argparse.Namespace) -> None:
    manifest = read_manifest(args.work_dir)
    translations = read_translations(args.work_dir)
    source_dir = args.work_dir / manifest.get("source_dir", "source")
    if not source_dir.exists():
        fail(f"missing source directory: {source_dir}")

    ET.register_namespace("", XHTML_NAMESPACE)
    slots_by_document: dict[str, list[dict]] = {}
    for slot in manifest.get("slots", []):
        slots_by_document.setdefault(slot["document"], []).append(slot)

    applied = 0
    for document, slots in slots_by_document.items():
        applied += apply_translations_to_document(
            source_dir,
            document,
            slots,
            translations,
            args.allow_missing,
        )

    write_epub(source_dir, args.output)
    print(f"DONE: applied_text_nodes={applied}")
    print(f"OUTPUT: {args.output.resolve()}")


def main() -> None:
    args = parse_args()
    if args.command == "prepare":
        prepare_command(args)
    elif args.command == "check":
        check_command(args)
    elif args.command == "build":
        build_command(args)
    else:
        fail(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
