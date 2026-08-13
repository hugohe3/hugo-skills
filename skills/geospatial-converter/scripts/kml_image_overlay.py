#!/usr/bin/env python3
"""Drape a screenshot over a KML polygon and package the result as KMZ."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import zipfile


KML_NS = "http://www.opengis.net/kml/2.2"
GX_NS = "http://www.google.com/kml/ext/2.2"
SUPPORTED_IMAGES = {".jpg", ".jpeg", ".png"}


def _load_pillow() -> tuple[Any, Any, Any]:
    try:
        from PIL import Image, ImageChops, ImageDraw
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'Pillow'. Install resources/requirements.txt first."
        ) from exc
    return Image, ImageChops, ImageDraw


def _namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return KML_NS


def _normalize_namespace(root: ET.Element) -> str:
    if root.tag.startswith("{"):
        return _namespace(root.tag)
    for element in root.iter():
        if isinstance(element.tag, str) and not element.tag.startswith("{"):
            element.tag = _qualified(KML_NS, element.tag)
    return KML_NS


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _qualified(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _parse_coordinates(text: str | None) -> list[tuple[float, float]]:
    if not text:
        raise ValueError("Polygon has no coordinates")
    points: list[tuple[float, float]] = []
    for token in text.split():
        values = token.split(",")
        if len(values) < 2:
            raise ValueError(f"Invalid KML coordinate tuple: {token!r}")
        try:
            longitude = float(values[0])
            latitude = float(values[1])
        except ValueError as exc:
            raise ValueError(f"Invalid KML coordinate tuple: {token!r}") from exc
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            raise ValueError(f"Non-finite KML coordinate tuple: {token!r}")
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError(
                "KML GroundOverlay requires WGS84 longitude/latitude coordinates; "
                f"found {longitude},{latitude}"
            )
        points.append((longitude, latitude))
    if len(points) > 1 and points[0] == points[-1]:
        points.pop()
    if len(points) < 3:
        raise ValueError("Polygon outer ring must contain at least three unique vertices")
    return points


def _ring_coordinates(element: ET.Element) -> list[tuple[float, float]]:
    coordinate_element = next(
        (child for child in element.iter() if _local_name(child.tag) == "coordinates"),
        None,
    )
    if coordinate_element is None:
        raise ValueError("Polygon boundary has no coordinates element")
    return _parse_coordinates(coordinate_element.text)


def _polygon_rings(polygon: ET.Element) -> tuple[list[tuple[float, float]], list[list[tuple[float, float]]]]:
    outer_element = next(
        (child for child in polygon if _local_name(child.tag) == "outerBoundaryIs"),
        None,
    )
    if outer_element is None:
        raise ValueError("Polygon has no outerBoundaryIs")
    outer = _ring_coordinates(outer_element)
    holes = [
        _ring_coordinates(child)
        for child in polygon
        if _local_name(child.tag) == "innerBoundaryIs"
    ]
    return outer, holes


def _placemark_name(placemark: ET.Element, index: int) -> str:
    name_element = next(
        (child for child in placemark if _local_name(child.tag) == "name"),
        None,
    )
    name = (name_element.text or "").strip() if name_element is not None else ""
    return name or f"Polygon {index}"


def _polygon_candidates(root: ET.Element) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for placemark in (element for element in root.iter() if _local_name(element.tag) == "Placemark"):
        for polygon in (element for element in placemark.iter() if _local_name(element.tag) == "Polygon"):
            candidates.append(
                {
                    "polygon": polygon,
                    "placemark": placemark,
                    "name": _placemark_name(placemark, len(candidates) + 1),
                }
            )
    return candidates


def _select_polygon(
    candidates: list[dict[str, Any]],
    polygon_index: int | None,
    polygon_name: str | None,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("No Polygon geometry found in the KML")
    if polygon_index is not None:
        if not 1 <= polygon_index <= len(candidates):
            raise ValueError(f"Polygon index must be between 1 and {len(candidates)}")
        return candidates[polygon_index - 1]
    if polygon_name:
        matches = [candidate for candidate in candidates if candidate["name"] == polygon_name]
        if len(matches) != 1:
            raise ValueError(
                f"Polygon name {polygon_name!r} matched {len(matches)} polygons; "
                "use --polygon-index"
            )
        return matches[0]
    if len(candidates) != 1:
        listing = ", ".join(
            f"{index}:{candidate['name']}"
            for index, candidate in enumerate(candidates, start=1)
        )
        raise ValueError(f"KML contains multiple polygons ({listing}); select one")
    return candidates[0]


def _unique_extreme_index(values: list[float], *, largest: bool) -> int | None:
    target = max(values) if largest else min(values)
    matches = [
        index
        for index, value in enumerate(values)
        if math.isclose(value, target, rel_tol=1e-12, abs_tol=1e-12)
    ]
    return matches[0] if len(matches) == 1 else None


def _ordered_convex_quad(points: list[tuple[float, float]]) -> list[tuple[float, float]] | None:
    if len(points) != 4 or len(set(points)) != 4:
        return None
    west = min(point[0] for point in points)
    east = max(point[0] for point in points)
    south = min(point[1] for point in points)
    north = max(point[1] for point in points)
    if east == west or north == south:
        return None

    normalized = [
        ((longitude - west) / (east - west), (latitude - south) / (north - south))
        for longitude, latitude in points
    ]
    sums = [x + y for x, y in normalized]
    differences = [x - y for x, y in normalized]
    indices = [
        _unique_extreme_index(sums, largest=False),
        _unique_extreme_index(differences, largest=True),
        _unique_extreme_index(sums, largest=True),
        _unique_extreme_index(differences, largest=False),
    ]
    if any(index is None for index in indices) or len(set(indices)) != 4:
        return None
    ordered = [points[index] for index in indices if index is not None]
    cross_products = []
    for index in range(4):
        first = ordered[index]
        second = ordered[(index + 1) % 4]
        third = ordered[(index + 2) % 4]
        cross_products.append(
            (second[0] - first[0]) * (third[1] - second[1])
            - (second[1] - first[1]) * (third[0] - second[0])
        )
    if any(value <= 0 for value in cross_products):
        return None
    return ordered


def _validated_bounds(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    west = min(point[0] for point in points)
    east = max(point[0] for point in points)
    south = min(point[1] for point in points)
    north = max(point[1] for point in points)
    if east == west or north == south:
        raise ValueError("Polygon bounds have zero width or height")
    if east - west > 180:
        raise ValueError("Polygons crossing the antimeridian are not supported")
    return west, south, east, north


def _image_pixel_points(
    ring: list[tuple[float, float]],
    bounds: tuple[float, float, float, float],
    size: tuple[int, int],
) -> list[tuple[float, float]]:
    west, south, east, north = bounds
    width, height = size
    return [
        (
            (longitude - west) / (east - west) * (width - 1),
            (north - latitude) / (north - south) * (height - 1),
        )
        for longitude, latitude in ring
    ]


def _masked_png(
    image_path: Path,
    outer: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]],
    bounds: tuple[float, float, float, float],
    output_path: Path,
    Image: Any,
    ImageChops: Any,
    ImageDraw: Any,
) -> tuple[int, int]:
    with Image.open(image_path) as source:
        image = source.convert("RGBA")
    mask = Image.new("L", image.size, 0)
    drawing = ImageDraw.Draw(mask)
    drawing.polygon(_image_pixel_points(outer, bounds, image.size), fill=255)
    for hole in holes:
        drawing.polygon(_image_pixel_points(hole, bounds, image.size), fill=0)
    image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
    image.save(output_path, format="PNG")
    return image.size


def _add_text(parent: ET.Element, namespace: str, name: str, value: Any) -> ET.Element:
    element = ET.SubElement(parent, _qualified(namespace, name))
    element.text = str(value)
    return element


def _add_overlay(
    parent: ET.Element,
    namespace: str,
    name: str,
    image_href: str,
    opacity: float,
    draw_order: int,
    quad: list[tuple[float, float]] | None,
    bounds: tuple[float, float, float, float],
) -> None:
    overlay = ET.SubElement(parent, _qualified(namespace, "GroundOverlay"))
    _add_text(overlay, namespace, "name", name)
    _add_text(overlay, namespace, "color", f"{round(opacity * 255):02x}ffffff")
    _add_text(overlay, namespace, "drawOrder", draw_order)
    icon = ET.SubElement(overlay, _qualified(namespace, "Icon"))
    _add_text(icon, namespace, "href", image_href)
    _add_text(overlay, namespace, "altitudeMode", "clampToGround")
    if quad:
        lat_lon_quad = ET.SubElement(overlay, _qualified(GX_NS, "LatLonQuad"))
        _add_text(
            lat_lon_quad,
            namespace,
            "coordinates",
            " ".join(f"{longitude:.12g},{latitude:.12g}" for longitude, latitude in quad),
        )
    else:
        west, south, east, north = bounds
        box = ET.SubElement(overlay, _qualified(namespace, "LatLonBox"))
        _add_text(box, namespace, "north", north)
        _add_text(box, namespace, "south", south)
        _add_text(box, namespace, "east", east)
        _add_text(box, namespace, "west", west)


def _local_assets(root: ET.Element, input_dir: Path) -> tuple[list[tuple[Path, str]], list[str]]:
    assets: list[tuple[Path, str]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag) != "href" or not element.text:
            continue
        href = element.text.strip()
        parsed = urlparse(href)
        relative = PurePosixPath(parsed.path)
        if parsed.scheme or parsed.netloc or relative.is_absolute() or ".." in relative.parts:
            continue
        archive_name = relative.as_posix()
        if not archive_name or archive_name in seen:
            continue
        source = input_dir.joinpath(*relative.parts)
        if source.is_file():
            assets.append((source, archive_name))
            seen.add(archive_name)
        else:
            warnings.append(f"Referenced local asset not found: {href}")
    return assets, warnings


def _unique_overlay_name(existing: set[str], suffix: str) -> str:
    candidate = f"files/screenshot_overlay{suffix}"
    index = 2
    while candidate in existing or candidate in {"doc.kml", "overlay_report.json"}:
        candidate = f"files/screenshot_overlay_{index}{suffix}"
        index += 1
    return candidate


def create_overlay(
    input_path: Path,
    image_path: Path,
    output_path: Path,
    polygon_index: int | None,
    polygon_name: str | None,
    overlay_name: str,
    mode: str,
    opacity: float,
    draw_order: int,
    overwrite: bool,
    Image: Any,
    ImageChops: Any,
    ImageDraw: Any,
) -> dict[str, Any]:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output_path}; pass --overwrite to replace it")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        tree = ET.parse(input_path)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid KML XML: {input_path}") from exc
    root = tree.getroot()
    namespace = _normalize_namespace(root)
    ET.register_namespace("", namespace)
    ET.register_namespace("gx", GX_NS)

    candidates = _polygon_candidates(root)
    selected = _select_polygon(candidates, polygon_index, polygon_name)
    outer, holes = _polygon_rings(selected["polygon"])
    bounds = _validated_bounds(outer)
    ordered_quad = _ordered_convex_quad(outer) if not holes else None
    if mode == "quad" and ordered_quad is None:
        raise ValueError("Quad mode requires one convex four-corner polygon without holes")
    use_quad = ordered_quad is not None and mode != "clip"

    parent_map = {child: parent for parent in root.iter() for child in parent}
    overlay_parent = parent_map.get(selected["placemark"], root)
    source_assets, warnings = _local_assets(root, input_path.parent)
    existing_assets = {archive_name for _, archive_name in source_assets}
    original_overlay_count = sum(
        _local_name(element.tag) == "GroundOverlay" for element in root.iter()
    )

    with tempfile.TemporaryDirectory(
        prefix=".kml-image-overlay-",
        dir=output_path.parent,
    ) as temp_name:
        temp_dir = Path(temp_name)
        if use_quad:
            embedded_name = _unique_overlay_name(existing_assets, image_path.suffix.lower())
            embedded_image = image_path
            with Image.open(image_path) as image:
                image.verify()
            with Image.open(image_path) as image:
                image_size = image.size
            overlay_mode = "gx:LatLonQuad"
        else:
            embedded_name = _unique_overlay_name(existing_assets, ".png")
            embedded_image = temp_dir / "screenshot_overlay.png"
            image_size = _masked_png(
                image_path,
                outer,
                holes,
                bounds,
                embedded_image,
                Image,
                ImageChops,
                ImageDraw,
            )
            overlay_mode = "clipped LatLonBox"

        _add_overlay(
            overlay_parent,
            namespace,
            overlay_name,
            embedded_name,
            opacity,
            draw_order,
            ordered_quad if use_quad else None,
            bounds,
        )
        ET.indent(tree, space="  ")
        kml_path = temp_dir / "doc.kml"
        tree.write(kml_path, encoding="utf-8", xml_declaration=True)

        summary = {
            "source": str(input_path),
            "image": str(image_path),
            "output": str(output_path),
            "polygonIndex": candidates.index(selected) + 1,
            "polygonName": selected["name"],
            "polygonVertices": len(outer),
            "polygonHoles": len(holes),
            "overlayMode": overlay_mode,
            "imageSize": list(image_size),
            "opacity": opacity,
            "warnings": warnings,
        }
        report_path = temp_dir / "overlay_report.json"
        report_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        staged_output = temp_dir / output_path.name
        with zipfile.ZipFile(staged_output, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(kml_path, "doc.kml")
            archive.write(embedded_image, embedded_name)
            archive.write(report_path, "overlay_report.json")
            for source, archive_name in source_assets:
                if archive_name != embedded_name:
                    archive.write(source, archive_name)
        with zipfile.ZipFile(staged_output) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("KMZ integrity check failed")
            output_root = ET.fromstring(archive.read("doc.kml"))
            overlays = [
                element for element in output_root.iter() if _local_name(element.tag) == "GroundOverlay"
            ]
            if len(overlays) != original_overlay_count + 1 or embedded_name not in archive.namelist():
                raise RuntimeError("KMZ overlay validation failed")
            with Image.open(BytesIO(archive.read(embedded_name))) as embedded:
                embedded.verify()
        os.replace(staged_output, output_path)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Overlay a screenshot on a KML polygon and create a portable KMZ."
    )
    parser.add_argument("kml", type=Path, help="Input .kml file")
    parser.add_argument("image", type=Path, help="Screenshot in PNG or JPEG format")
    parser.add_argument("-o", "--output", type=Path)
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--polygon-index", type=int, help="One-based polygon index")
    selector.add_argument("--polygon-name", help="Exact Placemark name")
    parser.add_argument("--name", help="GroundOverlay name; defaults to the image filename")
    parser.add_argument("--mode", choices=("auto", "quad", "clip"), default="auto")
    parser.add_argument("--opacity", type=float, default=1.0)
    parser.add_argument("--draw-order", type=int, default=1)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        input_path = args.kml.resolve()
        image_path = args.image.resolve()
        output_path = (args.output or input_path.with_name(f"{input_path.stem}_overlay.kmz")).resolve()
        if not input_path.is_file() or input_path.suffix.lower() != ".kml":
            raise ValueError(f"Input must be an existing .kml file: {input_path}")
        if not image_path.is_file() or image_path.suffix.lower() not in SUPPORTED_IMAGES:
            raise ValueError(f"Image must be an existing PNG or JPEG file: {image_path}")
        if output_path.suffix.lower() != ".kmz":
            raise ValueError("Output must be a .kmz file")
        if not 0 < args.opacity <= 1:
            raise ValueError("Opacity must be greater than 0 and at most 1")
        Image, ImageChops, ImageDraw = _load_pillow()
        summary = create_overlay(
            input_path,
            image_path,
            output_path,
            args.polygon_index,
            args.polygon_name,
            args.name or image_path.stem,
            args.mode,
            args.opacity,
            args.draw_order,
            args.overwrite,
            Image,
            ImageChops,
            ImageDraw,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUTPUT: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
