#!/usr/bin/env python3
"""Validate supported diagram source files with offline structural checks."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import math
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_by_name(parent: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in parent if local_name(child.tag) == name), None)


def decode_drawio_model(diagram: ET.Element, result: ValidationResult, page_label: str) -> ET.Element | None:
    model = child_by_name(diagram, "mxGraphModel")
    if model is not None:
        return model

    payload = (diagram.text or "").strip()
    if not payload:
        result.error(f"{page_label}: diagram does not contain mxGraphModel data")
        return None

    try:
        compressed = base64.b64decode(payload, validate=True)
        encoded_xml = zlib.decompress(compressed, -zlib.MAX_WBITS).decode("utf-8")
        xml_text = urllib.parse.unquote(encoded_xml)
        model = ET.fromstring(xml_text)
    except (binascii.Error, UnicodeDecodeError, zlib.error, ET.ParseError) as exc:
        result.error(f"{page_label}: compressed diagram cannot be decoded: {exc}")
        return None

    if local_name(model.tag) != "mxGraphModel":
        result.error(f"{page_label}: decoded root is not mxGraphModel")
        return None
    return model


def validate_drawio(path: Path) -> ValidationResult:
    result = ValidationResult()
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        result.error(f"cannot parse XML: {exc}")
        return result

    if local_name(root.tag) != "mxfile":
        result.error("root element must be mxfile")
        return result

    diagrams = [child for child in root if local_name(child.tag) == "diagram"]
    if not diagrams:
        result.error("mxfile must contain at least one diagram")
        return result

    page_ids: set[str] = set()
    for index, diagram in enumerate(diagrams, start=1):
        page_label = diagram.get("name") or f"page {index}"
        page_id = diagram.get("id")
        if page_id:
            if page_id in page_ids:
                result.error(f"{page_label}: duplicate diagram id {page_id!r}")
            page_ids.add(page_id)
        else:
            result.warn(f"{page_label}: diagram id is missing")

        model = decode_drawio_model(diagram, result, page_label)
        if model is None:
            continue
        graph_root = child_by_name(model, "root")
        if graph_root is None:
            result.error(f"{page_label}: mxGraphModel must contain root")
            continue

        cell_ids: dict[str, ET.Element] = {}
        for element in graph_root:
            element_name = local_name(element.tag)
            if element_name == "mxCell":
                cell = element
                cell_id = cell.get("id")
            elif element_name in {"object", "UserObject"}:
                cell = child_by_name(element, "mxCell")
                cell_id = element.get("id") or (cell.get("id") if cell is not None else None)
                if cell is None:
                    result.error(f"{page_label}: {element_name} {cell_id!r} does not contain mxCell")
                    continue
            else:
                continue
            if not cell_id:
                result.error(f"{page_label}: mxCell without id")
                continue
            if cell_id in cell_ids:
                result.error(f"{page_label}: duplicate cell id {cell_id!r}")
            cell_ids[cell_id] = cell

        if "0" not in cell_ids:
            result.error(f"{page_label}: missing structural cell id '0'")
        if "1" not in cell_ids or cell_ids["1"].get("parent") != "0":
            result.error(f"{page_label}: missing structural cell id '1' with parent '0'")

        for cell_id, cell in cell_ids.items():
            parent = cell.get("parent")
            if cell_id != "0":
                if not parent:
                    result.error(f"{page_label}: cell {cell_id!r} has no parent")
                elif parent not in cell_ids:
                    result.error(f"{page_label}: cell {cell_id!r} references missing parent {parent!r}")

            is_vertex = cell.get("vertex") == "1"
            is_edge = cell.get("edge") == "1"
            if is_vertex and is_edge:
                result.error(f"{page_label}: cell {cell_id!r} cannot be both vertex and edge")

            geometry = child_by_name(cell, "mxGeometry")
            if is_vertex:
                if geometry is None:
                    result.error(f"{page_label}: vertex {cell_id!r} has no mxGeometry")
                else:
                    for field_name in ("width", "height"):
                        raw_value = geometry.get(field_name)
                        try:
                            value = float(raw_value) if raw_value is not None else 0.0
                        except ValueError:
                            value = -1.0
                        if not math.isfinite(value) or value <= 0:
                            result.error(
                                f"{page_label}: vertex {cell_id!r} has invalid {field_name} {raw_value!r}"
                            )

            if is_edge:
                if geometry is None or geometry.get("relative") != "1":
                    result.error(f"{page_label}: edge {cell_id!r} must have relative mxGeometry")
                for reference_name in ("source", "target"):
                    reference = cell.get(reference_name)
                    if reference and reference not in cell_ids:
                        result.error(
                            f"{page_label}: edge {cell_id!r} references missing {reference_name} {reference!r}"
                        )
                    if not reference:
                        result.warn(f"{page_label}: edge {cell_id!r} has no {reference_name}")

    return result


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_binding(
    result: ValidationResult,
    element_id: str,
    field_name: str,
    binding: Any,
    element_ids: set[str],
) -> None:
    if binding is None:
        return
    if not isinstance(binding, dict):
        result.error(f"element {element_id!r}: {field_name} must be an object or null")
        return
    target_id = binding.get("elementId")
    if not isinstance(target_id, str) or target_id not in element_ids:
        result.error(f"element {element_id!r}: {field_name} references missing element {target_id!r}")


def validate_excalidraw(path: Path) -> ValidationResult:
    result = ValidationResult()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.error(f"cannot parse JSON: {exc}")
        return result

    if not isinstance(data, dict):
        result.error("top-level JSON value must be an object")
        return result
    if data.get("type") != "excalidraw":
        result.error("top-level type must be 'excalidraw'")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        result.error("top-level version must be a positive integer")

    elements = data.get("elements")
    if not isinstance(elements, list):
        result.error("top-level elements must be an array")
        return result
    if not elements:
        result.warn("scene has no elements")

    element_ids: set[str] = set()
    valid_elements: list[dict[str, Any]] = []
    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            result.error(f"elements[{index}] must be an object")
            continue
        element_id = element.get("id")
        if not isinstance(element_id, str) or not element_id:
            result.error(f"elements[{index}] has no valid id")
            continue
        if element_id in element_ids:
            result.error(f"duplicate element id {element_id!r}")
        element_ids.add(element_id)
        valid_elements.append(element)

    files = data.get("files", {})
    if not isinstance(files, dict):
        result.error("top-level files must be an object when present")
        files = {}

    for element in valid_elements:
        element_id = element["id"]
        element_type = element.get("type")
        if not isinstance(element_type, str) or not element_type:
            result.error(f"element {element_id!r}: type must be a non-empty string")

        if not element.get("isDeleted", False):
            for field_name in ("x", "y", "width", "height"):
                value = element.get(field_name)
                if not is_finite_number(value):
                    result.error(f"element {element_id!r}: {field_name} must be a finite number")
            for field_name in ("width", "height"):
                value = element.get(field_name)
                if is_finite_number(value) and value < 0:
                    result.error(f"element {element_id!r}: {field_name} cannot be negative")

        if element_type == "text":
            for field_name in ("text", "originalText"):
                if not isinstance(element.get(field_name), str):
                    result.error(f"element {element_id!r}: {field_name} must be a string")

        if element_type in {"arrow", "line"}:
            points = element.get("points")
            if not isinstance(points, list) or len(points) < 2:
                result.error(f"element {element_id!r}: linear element needs at least two points")
            elif any(
                not isinstance(point, list)
                or len(point) != 2
                or not all(is_finite_number(coordinate) for coordinate in point)
                for point in points
            ):
                result.error(f"element {element_id!r}: points must contain finite [x, y] pairs")
            validate_binding(result, element_id, "startBinding", element.get("startBinding"), element_ids)
            validate_binding(result, element_id, "endBinding", element.get("endBinding"), element_ids)

        for reference_name in ("containerId", "frameId"):
            reference = element.get(reference_name)
            if reference is not None and (not isinstance(reference, str) or reference not in element_ids):
                result.error(
                    f"element {element_id!r}: {reference_name} references missing element {reference!r}"
                )

        bound_elements = element.get("boundElements")
        if bound_elements is not None:
            if not isinstance(bound_elements, list):
                result.error(f"element {element_id!r}: boundElements must be an array or null")
            else:
                for binding in bound_elements:
                    bound_id = binding.get("id") if isinstance(binding, dict) else None
                    if not isinstance(bound_id, str) or bound_id not in element_ids:
                        result.error(
                            f"element {element_id!r}: boundElements references missing element {bound_id!r}"
                        )

        if element_type == "image":
            file_id = element.get("fileId")
            if not isinstance(file_id, str) or file_id not in files:
                result.error(f"element {element_id!r}: image fileId {file_id!r} is missing from files")

    app_state = data.get("appState")
    if app_state is not None and not isinstance(app_state, dict):
        result.error("top-level appState must be an object when present")

    return result


def read_source_text(path: Path, result: ValidationResult) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        result.error(f"cannot read UTF-8 text: {exc}")
        return None


def check_balanced_braces(
    text: str,
    result: ValidationResult,
    *,
    line_comment_markers: tuple[str, ...],
) -> None:
    depth = 0
    line_number = 1
    line_start = 0
    index = 0
    quote: str | None = None

    while index < len(text):
        char = text[index]
        if char == "\n":
            line_number += 1
            line_start = index + 1

        if quote is not None:
            if char == "\\":
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue

        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                result.error(f"unclosed block comment starting on line {line_number}")
                return
            line_number += text.count("\n", index, end + 2)
            last_newline = text.rfind("\n", index, end + 2)
            if last_newline >= 0:
                line_start = last_newline + 1
            index = end + 2
            continue

        matched_comment = False
        for marker in line_comment_markers:
            if not text.startswith(marker, index):
                continue
            if marker == "#" and text[line_start:index].strip():
                continue
            end = text.find("\n", index + len(marker))
            index = len(text) if end < 0 else end
            matched_comment = True
            break
        if matched_comment:
            continue

        if char in {'"', "'", "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            if depth == 0:
                result.error(f"unexpected closing brace on line {line_number}")
                return
            depth -= 1
        index += 1

    if quote is not None:
        result.error("unclosed quoted string")
    if depth:
        result.error(f"{depth} unclosed opening brace(s)")


def strip_leading_comments(text: str) -> str:
    pattern = re.compile(r"\A(?:\s+|//[^\n]*(?:\n|\Z)|\#[^\n]*(?:\n|\Z)|/\*.*?\*/)*", re.DOTALL)
    return text[pattern.match(text).end() :]


MERMAID_DIAGRAM_TYPES = {
    "architecture-beta",
    "block-beta",
    "classDiagram",
    "C4Component",
    "C4Container",
    "C4Context",
    "C4Deployment",
    "C4Dynamic",
    "cynefin-beta",
    "erDiagram",
    "flowchart",
    "gantt",
    "gitGraph",
    "graph",
    "ishikawa-beta",
    "journey",
    "kanban",
    "mindmap",
    "packet-beta",
    "pie",
    "quadrantChart",
    "radar-beta",
    "requirementDiagram",
    "sankey-beta",
    "sequenceDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "timeline",
    "treeView-beta",
    "treemap-beta",
    "venn-beta",
    "wardley-beta",
    "xychart-beta",
    "zenuml",
}


def validate_mermaid(path: Path) -> ValidationResult:
    result = ValidationResult()
    text = read_source_text(path, result)
    if text is None:
        return result
    if "```" in text:
        result.error("native Mermaid source must not contain Markdown code fences")
        return result

    lines = text.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index < len(lines) and lines[index].strip() == "---":
        index += 1
        while index < len(lines) and lines[index].strip() != "---":
            index += 1
        if index >= len(lines):
            result.error("Mermaid YAML frontmatter is not closed")
            return result
        index += 1

    while index < len(lines):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("%%"):
            break
        index += 1
    if index >= len(lines):
        result.error("Mermaid source has no diagram declaration")
        return result

    declaration = lines[index].strip().split(maxsplit=1)[0]
    if declaration not in MERMAID_DIAGRAM_TYPES:
        result.warn(
            f"unrecognized Mermaid diagram declaration {declaration!r}; validate with the project renderer"
        )
    if not any(line.strip() and not line.strip().startswith("%%") for line in lines[index + 1 :]):
        result.warn("Mermaid diagram has a declaration but no body")
    return result


def validate_plantuml(path: Path) -> ValidationResult:
    result = ValidationResult()
    text = read_source_text(path, result)
    if text is None:
        return result

    tokens = list(re.finditer(r"(?im)^\s*@(start|end)([A-Za-z0-9_]*)\b", text))
    if not tokens:
        result.error("PlantUML source must contain matching @start... and @end... directives")
        return result

    stack: list[tuple[str, int]] = []
    for token in tokens:
        action = token.group(1).lower()
        diagram_type = token.group(2).lower()
        line_number = text.count("\n", 0, token.start()) + 1
        if action == "start":
            stack.append((diagram_type, line_number))
            continue
        if not stack:
            result.error(f"unexpected @end{diagram_type} on line {line_number}")
            continue
        start_type, start_line = stack.pop()
        if diagram_type != start_type:
            result.error(
                f"@start{start_type} on line {start_line} is closed by @end{diagram_type} on line {line_number}"
            )

    for diagram_type, line_number in stack:
        result.error(f"@start{diagram_type} on line {line_number} is not closed")
    if re.search(r"(?im)^\s*!include(?:url)?\s+https?://", text):
        result.warn("PlantUML source includes a remote resource; validate only when the URL is trusted")
    return result


def validate_graphviz(path: Path) -> ValidationResult:
    result = ValidationResult()
    text = read_source_text(path, result)
    if text is None:
        return result
    source = strip_leading_comments(text)
    match = re.match(r"(?is)(?:strict\s+)?(digraph|graph)\b[^\{]*\{", source)
    if not match:
        result.error("DOT source must start with graph or digraph and an opening brace")
        return result
    check_balanced_braces(text, result, line_comment_markers=("//", "#"))
    edge_operator = "->" if match.group(1).lower() == "digraph" else "--"
    if edge_operator not in text:
        result.warn(f"DOT source contains no {edge_operator} edges")
    return result


def validate_d2(path: Path) -> ValidationResult:
    result = ValidationResult()
    text = read_source_text(path, result)
    if text is None:
        return result
    if not text.strip():
        result.error("D2 source is empty")
        return result
    check_balanced_braces(text, result, line_comment_markers=("#",))
    if "->" not in text and "<-" not in text and ":" not in text:
        result.warn("D2 source contains no visible relationship or object declaration")
    if re.search(r"https?://", text):
        result.warn("D2 source references a remote resource; validate only when the URL is trusted")
    return result


def validate_structurizr(path: Path) -> ValidationResult:
    result = ValidationResult()
    text = read_source_text(path, result)
    if text is None:
        return result
    source = strip_leading_comments(text)
    if not re.search(r"\bworkspace\b", source):
        result.error("Structurizr DSL must contain a workspace declaration")
    if not re.search(r"\bmodel\s*\{", source):
        result.error("Structurizr DSL must contain a model block")
    if not re.search(r"\bviews\s*\{", source):
        result.warn("Structurizr DSL has no views block; only default views may be generated")
    check_balanced_braces(text, result, line_comment_markers=("//",))
    if re.search(r"(?im)^\s*!(?:script|plugin)\b", text):
        result.warn("Structurizr DSL contains executable script or plugin directives")
    if re.search(r"(?im)^\s*!include\s+https?://", text):
        result.warn("Structurizr DSL includes a remote resource; validate only when the URL is trusted")
    return result


def parse_xml(path: Path, result: ValidationResult) -> ET.Element | None:
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        result.error(f"cannot parse XML: {exc}")
        return None


def namespace_uri(tag: str) -> str | None:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return None


def collect_xml_ids(root: ET.Element, result: ValidationResult) -> dict[str, ET.Element]:
    ids: dict[str, ET.Element] = {}
    for element in root.iter():
        element_id = element.get("id")
        if not element_id:
            continue
        if element_id in ids:
            result.error(f"duplicate XML id {element_id!r}")
        ids[element_id] = element
    return ids


BPMN_MODEL_NAMESPACE = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN_DI_NAMESPACE = "http://www.omg.org/spec/BPMN/20100524/DI"
DD_DI_NAMESPACE = "http://www.omg.org/spec/DD/20100524/DI"


def validate_bpmn(path: Path) -> ValidationResult:
    result = ValidationResult()
    root = parse_xml(path, result)
    if root is None:
        return result
    if local_name(root.tag) != "definitions" or namespace_uri(root.tag) != BPMN_MODEL_NAMESPACE:
        result.error("BPMN root must be definitions in the BPMN 2.0 model namespace")
        return result
    if not root.get("targetNamespace"):
        result.warn("BPMN definitions has no targetNamespace")

    ids = collect_xml_ids(root, result)
    model_elements = [
        element for element in root.iter() if namespace_uri(element.tag) == BPMN_MODEL_NAMESPACE
    ]
    if not any(local_name(element.tag) in {"process", "collaboration"} for element in model_elements):
        result.error("BPMN document must contain a process or collaboration")

    for element in model_elements:
        element_name = local_name(element.tag)
        if element_name not in {"sequenceFlow", "messageFlow", "association"}:
            continue
        element_id = element.get("id") or element_name
        for reference_name in ("sourceRef", "targetRef"):
            reference = element.get(reference_name)
            if not reference:
                result.error(f"BPMN {element_id!r} has no {reference_name}")
            elif reference not in ids:
                result.error(f"BPMN {element_id!r} references missing {reference_name} {reference!r}")

    diagrams = [element for element in root.iter() if namespace_uri(element.tag) == BPMN_DI_NAMESPACE]
    if not any(local_name(element.tag) == "BPMNDiagram" for element in diagrams):
        result.error("BPMN document has no BPMNDiagram layout information")
        return result

    for element in diagrams:
        element_name = local_name(element.tag)
        reference = element.get("bpmnElement")
        if element_name in {"BPMNPlane", "BPMNShape", "BPMNEdge"}:
            if not reference:
                result.error(f"{element_name} {element.get('id')!r} has no bpmnElement reference")
            elif reference not in ids:
                result.error(
                    f"{element_name} {element.get('id')!r} references missing BPMN element {reference!r}"
                )
        if element_name == "BPMNEdge":
            waypoints = [
                child
                for child in element
                if local_name(child.tag) == "waypoint" and namespace_uri(child.tag) == DD_DI_NAMESPACE
            ]
            if len(waypoints) < 2:
                result.error(f"BPMNEdge {element.get('id')!r} must contain at least two waypoints")
    return result


GRAPHML_NAMESPACE = "http://graphml.graphdrawing.org/xmlns"


def validate_graphml(path: Path) -> ValidationResult:
    result = ValidationResult()
    root = parse_xml(path, result)
    if root is None:
        return result
    if local_name(root.tag) != "graphml" or namespace_uri(root.tag) != GRAPHML_NAMESPACE:
        result.error("GraphML root must be graphml in the GraphML namespace")
        return result

    keys: set[str] = set()
    node_ids: set[str] = set()
    graph_count = 0
    for element in root.iter():
        element_name = local_name(element.tag)
        if namespace_uri(element.tag) != GRAPHML_NAMESPACE:
            continue
        if element_name == "key":
            key_id = element.get("id")
            if not key_id:
                result.error("GraphML key has no id")
            elif key_id in keys:
                result.error(f"duplicate GraphML key id {key_id!r}")
            else:
                keys.add(key_id)
        elif element_name == "node":
            node_id = element.get("id")
            if not node_id:
                result.error("GraphML node has no id")
            elif node_id in node_ids:
                result.error(f"duplicate GraphML node id {node_id!r}")
            else:
                node_ids.add(node_id)
        elif element_name == "graph":
            graph_count += 1
            if element.get("edgedefault") not in {"directed", "undirected"}:
                result.error(f"GraphML graph {element.get('id')!r} has invalid edgedefault")

    if graph_count == 0:
        result.error("GraphML document must contain at least one graph")

    for element in root.iter():
        if namespace_uri(element.tag) != GRAPHML_NAMESPACE:
            continue
        element_name = local_name(element.tag)
        if element_name == "edge":
            edge_id = element.get("id") or "unnamed edge"
            for reference_name in ("source", "target"):
                reference = element.get(reference_name)
                if not reference:
                    result.error(f"GraphML edge {edge_id!r} has no {reference_name}")
                elif reference not in node_ids:
                    result.error(
                        f"GraphML edge {edge_id!r} references missing {reference_name} {reference!r}"
                    )
        elif element_name == "data":
            key_reference = element.get("key")
            if not key_reference:
                result.error("GraphML data element has no key reference")
            elif key_reference not in keys:
                result.error(f"GraphML data references missing key {key_reference!r}")
    return result


SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def validate_svg(path: Path) -> ValidationResult:
    result = ValidationResult()
    root = parse_xml(path, result)
    if root is None:
        return result
    if local_name(root.tag) != "svg" or namespace_uri(root.tag) != SVG_NAMESPACE:
        result.error("SVG root must be svg in the SVG namespace")
        return result

    view_box = root.get("viewBox")
    if not view_box:
        result.error("SVG root must define viewBox")
    else:
        try:
            values = [float(value) for value in re.split(r"[\s,]+", view_box.strip()) if value]
        except ValueError:
            values = []
        if len(values) != 4 or not all(math.isfinite(value) for value in values):
            result.error(f"SVG viewBox is invalid: {view_box!r}")
        elif values[2] <= 0 or values[3] <= 0:
            result.error("SVG viewBox width and height must be positive")

    ids = collect_xml_ids(root, result)
    visible_elements = 0
    has_title = False
    has_description = False
    for element in root.iter():
        element_name = local_name(element.tag)
        if element_name in {"script", "foreignObject"}:
            result.error(f"SVG contains disallowed active element {element_name!r}")
        if element_name == "title":
            has_title = True
        elif element_name == "desc":
            has_description = True
        elif element_name in {"circle", "ellipse", "image", "line", "path", "polygon", "polyline", "rect", "text", "use"}:
            visible_elements += 1

        for attribute_name, value in element.attrib.items():
            attribute_local_name = local_name(attribute_name)
            if attribute_local_name.lower().startswith("on"):
                result.error(
                    f"SVG element {element.get('id')!r} contains disallowed event attribute {attribute_local_name!r}"
                )
            if attribute_local_name == "href":
                if value.startswith("#"):
                    if value[1:] not in ids:
                        result.error(f"SVG reference {value!r} does not match an element id")
                elif not value.startswith("data:"):
                    result.warn(f"SVG contains external reference {value!r}")
            for referenced_id in re.findall(r"url\(\s*#([^\)\s]+)\s*\)", value):
                if referenced_id not in ids:
                    result.error(f"SVG url() reference {referenced_id!r} does not match an element id")

    if visible_elements == 0:
        result.warn("SVG contains no visible shape or text elements")
    if not has_title:
        result.warn("SVG has no title element")
    if not has_description:
        result.warn("SVG has no desc element")
    return result


Validator = Callable[[Path], ValidationResult]
VALIDATORS: dict[str, Validator] = {
    ".bpmn20.xml": validate_bpmn,
    ".bpmn": validate_bpmn,
    ".d2": validate_d2,
    ".dot": validate_graphviz,
    ".dsl": validate_structurizr,
    ".drawio": validate_drawio,
    ".excalidraw": validate_excalidraw,
    ".graphml": validate_graphml,
    ".gv": validate_graphviz,
    ".mermaid": validate_mermaid,
    ".mmd": validate_mermaid,
    ".pu": validate_plantuml,
    ".puml": validate_plantuml,
    ".svg": validate_svg,
}


def validate_path(path: Path) -> ValidationResult:
    file_name = path.name.lower()
    matched_suffix = next(
        (suffix for suffix in sorted(VALIDATORS, key=len, reverse=True) if file_name.endswith(suffix)),
        None,
    )
    validator = VALIDATORS.get(matched_suffix) if matched_suffix else None
    if validator is None:
        supported = ", ".join(sorted(VALIDATORS))
        return ValidationResult(errors=[f"unsupported file name {path.name!r}; expected one of: {supported}"])
    if not path.is_file():
        return ValidationResult(errors=["file does not exist or is not a regular file"])
    return validator(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate supported diagram source files.")
    parser.add_argument("paths", nargs="+", type=Path, help="Diagram files to validate.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    has_errors = False
    for path in args.paths:
        result = validate_path(path)
        if result.errors:
            has_errors = True
            print(f"INVALID: {path}")
            for message in result.errors:
                print(f"  ERROR: {message}")
        else:
            print(f"VALID: {path}")
        for message in result.warnings:
            print(f"  WARNING: {message}")
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
