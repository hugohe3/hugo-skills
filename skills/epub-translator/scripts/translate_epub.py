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
OPF_NAMESPACE = "http://www.idpf.org/2007/opf"
DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
NCX_NAMESPACE = "http://www.daisy.org/z3986/2005/ncx/"
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
    tags: list[str]


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
        "--target-language-code",
        default="zh-Hans",
        help="EPUB language code written to metadata during build",
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
    source_root = source_dir.resolve()
    with zipfile.ZipFile(input_path, "r") as epub:
        for info in epub.infolist():
            member_path = Path(info.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                fail(f"unsafe EPUB entry path: {info.filename}")

            target_path = (source_dir / member_path).resolve()
            if target_path != source_root and source_root not in target_path.parents:
                fail(f"unsafe EPUB entry path: {info.filename}")

            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            with epub.open(info, "r") as source, target_path.open("wb") as target:
                shutil.copyfileobj(source, target)


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


def resolve_manifest_href(base_dir: Path, href: str) -> Path:
    normalized = posixpath.normpath(href.split("#", 1)[0])
    return base_dir / normalized


def append_unique(paths: list[Path], path: Path) -> None:
    if path not in paths:
        paths.append(path)


def get_epub_translation_documents(opf_path: Path) -> tuple[list[Path], list[Path]]:
    tree = ET.parse(opf_path)
    root = tree.getroot()
    manifest: dict[str, dict[str, str]] = {}
    spine_ids: list[str] = []
    spine_toc_id = ""

    for element in root.iter():
        name = local_name(element.tag)
        if name == "item":
            item_id = element.attrib.get("id")
            href = element.attrib.get("href")
            media_type = element.attrib.get("media-type", "")
            if item_id and href:
                manifest[item_id] = {
                    "href": href,
                    "media_type": media_type,
                    "properties": element.attrib.get("properties", ""),
                }
        elif name == "spine":
            spine_toc_id = element.attrib.get("toc", "")
        elif name == "itemref":
            itemref = element.attrib.get("idref")
            if itemref:
                spine_ids.append(itemref)

    xhtml_documents: list[Path] = []
    xml_documents: list[Path] = []
    base_dir = opf_path.parent
    for item_id in spine_ids:
        item = manifest.get(item_id)
        if not item:
            continue
        href = item["href"]
        media_type = item["media_type"]
        if media_type not in {"application/xhtml+xml", "text/html"}:
            continue
        append_unique(xhtml_documents, resolve_manifest_href(base_dir, href))

    for item_id, item in manifest.items():
        href = item["href"]
        media_type = item["media_type"]
        properties = set(item["properties"].split())
        if media_type in {"application/xhtml+xml", "text/html"} and "nav" in properties:
            append_unique(xhtml_documents, resolve_manifest_href(base_dir, href))
        if media_type == "application/x-dtbncx+xml" or item_id == spine_toc_id:
            append_unique(xml_documents, resolve_manifest_href(base_dir, href))

    append_unique(xml_documents, opf_path)
    return xhtml_documents, xml_documents


PLACEHOLDER_RE = re.compile(r"\[t:\d+\]")
BLOCK_TAGS = {
    "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "div", "blockquote", 
    "td", "th", "dt", "dd", "title", "caption"
}


def strip_xhtml_namespace(serialized: str) -> str:
    return serialized.replace(f' xmlns="{XHTML_NAMESPACE}"', "")


def element_tags(element: ET.Element) -> tuple[str, str] | tuple[str]:
    empty_element = ET.Element(element.tag, dict(element.attrib))
    if not list(element) and not element.text:
        tag = ET.tostring(empty_element, encoding="unicode", short_empty_elements=True)
        return (strip_xhtml_namespace(tag),)

    serialized = ET.tostring(empty_element, encoding="unicode", short_empty_elements=False)
    serialized = strip_xhtml_namespace(serialized)
    close_index = serialized.rfind("</")
    if close_index == -1:
        return (serialized,)
    return serialized[:close_index], serialized[close_index:]


def append_tag_placeholder(parts: list[str], tags: list[str], tag: str) -> None:
    index = len(tags)
    tags.append(tag)
    parts.append(f"[t:{index}]")


def serialize_block(
    element: ET.Element,
    processed_nodes: set[tuple[int, str]]
) -> tuple[str, list[str]]:
    processed_nodes.add((id(element), "text"))
    
    def recurse(el: ET.Element):
        processed_nodes.add((id(el), "text"))
        for child in el:
            processed_nodes.add((id(child), "text"))
            processed_nodes.add((id(child), "tail"))
            recurse(child)
            
    recurse(element)
    
    parts: list[str] = []
    tags: list[str] = []

    def append_child(child: ET.Element) -> None:
        child_tags = element_tags(child)
        if len(child_tags) == 1:
            append_tag_placeholder(parts, tags, child_tags[0])
        else:
            start_tag, end_tag = child_tags
            append_tag_placeholder(parts, tags, start_tag)
            if child.text:
                parts.append(child.text)
            for grandchild in child:
                append_child(grandchild)
            append_tag_placeholder(parts, tags, end_tag)

        if child.tail:
            parts.append(child.tail)

    if element.text:
        parts.append(element.text)
    for child in element:
        append_child(child)

    return "".join(parts), tags


def collect_text_slots(
    root: ET.Element,
    document: str,
    counters: dict[str, int]
) -> list[TextSlot]:
    processed_nodes: set[tuple[int, str]] = set()
    slots: list[TextSlot] = []
    
    leaf_blocks: list[tuple[ET.Element, list[int]]] = []
    
    def find_leaf_blocks(element: ET.Element, path: list[int]):
        tag_name = local_name(element.tag).lower()
        if tag_name in SKIP_TAGS:
            return
            
        is_block = tag_name in BLOCK_TAGS
        has_child_block = any(local_name(child.tag).lower() in BLOCK_TAGS for child in element.iter() if child is not element)
        
        if is_block and not has_child_block:
            has_text = False
            for el in element.iter():
                if is_translatable_text(el.text or "") or (el is not element and is_translatable_text(el.tail or "")):
                    has_text = True
                    break
            if has_text:
                leaf_blocks.append((element, path))
                return
                
        for index, child in enumerate(list(element)):
            find_leaf_blocks(child, [*path, index])
            
    find_leaf_blocks(root, [])
    
    for block, path in leaf_blocks:
        serialized, tags = serialize_block(block, processed_nodes)
        counters["slot"] += 1
        slot_id = f"t{counters['slot']:06d}"
        slots.append(TextSlot(
            slot_id=slot_id,
            document=document,
            path=path,
            attribute="block",
            source=serialized,
            tags=tags
        ))
        
    def collect_fallback(element: ET.Element, path: list[int], inherited_skip: bool = False):
        tag_name = local_name(element.tag).lower()
        skip = inherited_skip or tag_name in SKIP_TAGS
        
        if not skip:
            node_key = (id(element), "text")
            if node_key not in processed_nodes and is_translatable_text(element.text or ""):
                counters["slot"] += 1
                slot_id = f"t{counters['slot']:06d}"
                slots.append(TextSlot(
                    slot_id=slot_id,
                    document=document,
                    path=path,
                    attribute="text",
                    source=element.text or "",
                    tags=[]
                ))
                
        for index, child in enumerate(list(element)):
            child_path = [*path, index]
            collect_fallback(child, child_path, skip)
            
            if not skip:
                node_key = (id(child), "tail")
                if node_key not in processed_nodes and is_translatable_text(child.tail or ""):
                    counters["slot"] += 1
                    slot_id = f"t{counters['slot']:06d}"
                    slots.append(TextSlot(
                        slot_id=slot_id,
                        document=document,
                        path=child_path,
                        attribute="tail",
                        source=child.tail or "",
                        tags=[]
                    ))
                    
    collect_fallback(root, [])
    return slots


def collect_ncx_slots(
    root: ET.Element,
    document: str,
    counters: dict[str, int]
) -> list[TextSlot]:
    slots: list[TextSlot] = []

    def visit(element: ET.Element, path: list[int]) -> None:
        if local_name(element.tag).lower() == "text" and is_translatable_text(element.text or ""):
            counters["slot"] += 1
            slot_id = f"t{counters['slot']:06d}"
            slots.append(TextSlot(
                slot_id=slot_id,
                document=document,
                path=path,
                attribute="text",
                source=element.text or "",
                tags=[],
            ))

        for index, child in enumerate(list(element)):
            visit(child, [*path, index])

    visit(root, [])
    return slots


def collect_opf_metadata_slots(
    root: ET.Element,
    document: str,
    counters: dict[str, int]
) -> list[TextSlot]:
    slots: list[TextSlot] = []

    def visit(element: ET.Element, path: list[int]) -> None:
        if local_name(element.tag).lower() == "title" and is_translatable_text(element.text or ""):
            counters["slot"] += 1
            slot_id = f"t{counters['slot']:06d}"
            slots.append(TextSlot(
                slot_id=slot_id,
                document=document,
                path=path,
                attribute="text",
                source=element.text or "",
                tags=[],
            ))

        for index, child in enumerate(list(element)):
            visit(child, [*path, index])

    visit(root, [])
    return slots


def batch_slots(slots: list[TextSlot], max_chars: int) -> Iterable[list[TextSlot]]:
    batch: list[TextSlot] = []
    current_chars = 0
    for slot in slots:
        slot_len = len(slot.source)
        # Limit by both character count and total items (max 20) per batch
        if batch and (current_chars + slot_len > max_chars or len(batch) >= 20):
            yield batch
            batch = []
            current_chars = 0
        batch.append(slot)
        current_chars += slot_len
    if batch:
        yield batch


def validate_placeholders(slot: dict, translation: str, document: str, allow_missing: bool) -> bool:
    tags = slot.get("tags", [])
    if not tags:
        return True

    expected = [f"[t:{index}]" for index in range(len(tags))]
    actual = PLACEHOLDER_RE.findall(translation)
    if actual == expected:
        return True

    print(
        f"ERROR: {slot['id']} in {document}: placeholder mismatch. "
        f"expected={expected} actual={actual}",
        file=sys.stderr,
    )
    print(f"Original source: {slot['source']}", file=sys.stderr)
    print(f"Translated text: {translation}", file=sys.stderr)
    if allow_missing:
        return False
    raise SystemExit(1)


def validate_placeholders_for_check(slot: dict, translation: str, location: str) -> str | None:
    tags = slot.get("tags", [])
    if not tags:
        return None

    expected = [f"[t:{index}]" for index in range(len(tags))]
    actual = PLACEHOLDER_RE.findall(translation)
    if actual == expected:
        return None
    return f"{location}: placeholder mismatch for {slot['id']}: expected={expected} actual={actual}"


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
    xhtml_documents, xml_documents = get_epub_translation_documents(opf_path)
    if not xhtml_documents and not xml_documents:
        fail("no XHTML spine documents found")

    ET.register_namespace("", XHTML_NAMESPACE)
    ET.register_namespace("opf", OPF_NAMESPACE)
    ET.register_namespace("dc", DC_NAMESPACE)
    ET.register_namespace("ncx", NCX_NAMESPACE)
    counters = {"slot": 0}
    all_slots: list[TextSlot] = []
    document_records: list[str] = []

    for document_path in xhtml_documents:
        relative = document_path.relative_to(source_dir).as_posix()
        document_records.append(relative)
        try:
            tree = ET.parse(document_path)
        except ET.ParseError as error:
            print(f"SKIP: {relative}: XML parse error: {error}", file=sys.stderr)
            continue
        all_slots.extend(collect_text_slots(tree.getroot(), relative, counters))

    for document_path in xml_documents:
        relative = document_path.relative_to(source_dir).as_posix()
        document_records.append(relative)
        try:
            tree = ET.parse(document_path)
        except ET.ParseError as error:
            print(f"SKIP: {relative}: XML parse error: {error}", file=sys.stderr)
            continue
        root = tree.getroot()
        if document_path == opf_path:
            all_slots.extend(collect_opf_metadata_slots(root, relative, counters))
        else:
            all_slots.extend(collect_ncx_slots(root, relative, counters))

    manifest = {
        "input": str(args.input),
        "source_language": args.source_language,
        "target_language": args.target_language,
        "target_language_code": args.target_language_code,
        "source_dir": "source",
        "chunks_dir": "chunks",
        "translated_dir": "translated",
        "opf_document": opf_path.relative_to(source_dir).as_posix(),
        "documents": document_records,
        "slots": [
            {
                "id": slot.slot_id,
                "document": slot.document,
                "path": slot.path,
                "attribute": slot.attribute,
                "source": slot.source,
                "tags": slot.tags,
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


def read_translations(
    work_dir: Path,
    slots: list[dict],
    allow_missing: bool = False,
    validate_tags: bool = True,
) -> dict[str, str]:
    translated_dir = work_dir / "translated"
    if not translated_dir.exists():
        fail(f"missing translated directory: {translated_dir}")

    slot_by_id = {slot["id"]: slot for slot in slots}
    translations: dict[str, str] = {}
    errors: list[str] = []
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
                location = f"{path}:{line_number}"

                if not isinstance(slot_id, str) or not slot_id:
                    errors.append(f"{location}: missing or invalid id")
                    continue
                if slot_id not in slot_by_id:
                    errors.append(f"{location}: unknown id {slot_id}")
                    continue
                if slot_id in translations:
                    errors.append(f"{location}: duplicate id {slot_id}")
                    continue
                if not isinstance(translation, str):
                    errors.append(f"{location}: translation must be a string")
                    continue
                if not translation.strip():
                    if not allow_missing:
                        errors.append(f"{location}: blank translation for {slot_id}")
                    continue

                if validate_tags:
                    placeholder_error = validate_placeholders_for_check(
                        slot_by_id[slot_id],
                        translation,
                        location,
                    )
                    if placeholder_error:
                        errors.append(placeholder_error)
                        continue

                translations[slot_id] = translation

    if errors:
        for error in errors[:50]:
            print(f"ERROR: {error}", file=sys.stderr)
        if len(errors) > 50:
            print(f"ERROR: ... {len(errors) - 50} more validation errors", file=sys.stderr)
        raise SystemExit(1)

    return translations


def check_command(args: argparse.Namespace) -> None:
    manifest = read_manifest(args.work_dir)
    slots = manifest.get("slots", [])
    translations = read_translations(args.work_dir, slots)
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
        attribute = slot.get("attribute", "text")
        
        if attribute == "block":
            tags = slot.get("tags", [])
            translated_xml = translation
            if not validate_placeholders(slot, translation, document, allow_missing):
                continue
            # Restore original tags in placeholders
            for idx, tag in enumerate(tags):
                translated_xml = translated_xml.replace(f"[t:{idx}]", tag)
                
            # Verify if there are any leftover placeholders that were not restored
            leftover = re.findall(r"\[t:\d+\]", translated_xml)
            if leftover:
                print(f"ERROR: {slot_id} in {document}: Leftover placeholder tags {leftover} after restoration.", file=sys.stderr)
                print(f"Original source: {slot['source']}", file=sys.stderr)
                print(f"Translated text: {translation}", file=sys.stderr)
                if not allow_missing:
                    raise SystemExit(1)
                
            wrapper_xml = f'<root xmlns="{XHTML_NAMESPACE}">{translated_xml}</root>'
            try:
                temp_root = ET.fromstring(wrapper_xml)
                element.text = temp_root.text
                element[:] = list(temp_root)
            except ET.ParseError as error:
                print(f"ERROR: {slot_id} in {document}: XML parse error in translation: {error}", file=sys.stderr)
                print(f"Original source: {slot['source']}", file=sys.stderr)
                print(f"Translated text: {translation}", file=sys.stderr)
                print(f"Restored XML: {translated_xml}", file=sys.stderr)
                if allow_missing:
                    continue
                raise SystemExit(1)
        elif attribute == "text":
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


def update_opf_language(opf_path: Path, target_language_code: str) -> None:
    if not target_language_code or not opf_path.exists():
        return

    tree = ET.parse(opf_path)
    root = tree.getroot()
    updated = False
    for element in root.iter():
        if local_name(element.tag).lower() == "language":
            element.text = target_language_code
            updated = True

    if updated:
        tree.write(opf_path, encoding="utf-8", xml_declaration=True)


def build_command(args: argparse.Namespace) -> None:
    manifest = read_manifest(args.work_dir)
    slots = manifest.get("slots", [])
    translations = read_translations(
        args.work_dir,
        slots,
        allow_missing=args.allow_missing,
    )
    source_dir = args.work_dir / manifest.get("source_dir", "source")
    if not source_dir.exists():
        fail(f"missing source directory: {source_dir}")

    ET.register_namespace("", XHTML_NAMESPACE)
    ET.register_namespace("opf", OPF_NAMESPACE)
    ET.register_namespace("dc", DC_NAMESPACE)
    ET.register_namespace("ncx", NCX_NAMESPACE)
    slots_by_document: dict[str, list[dict]] = {}
    for slot in slots:
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

    opf_document = manifest.get("opf_document")
    if isinstance(opf_document, str):
        update_opf_language(
            source_dir / opf_document,
            manifest.get("target_language_code", "zh-Hans"),
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
