#!/usr/bin/env python3
"""Export basic Shapefile geometries to an AutoCAD 2000 DXF."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


POINT_TYPES = {1, 11, 21}
POLYLINE_TYPES = {3, 13, 23}
POLYGON_TYPES = {5, 15, 25}
MULTIPOINT_TYPES = {8, 18, 28}


def _load_dependencies() -> tuple[Any, Any]:
    try:
        import shapefile
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'pyshp'. Install resources/requirements.txt first."
        ) from exc
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'ezdxf'. Install resources/requirements.txt first."
        ) from exc
    return shapefile, ezdxf


def _layer_name(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")
    if not name:
        name = "GEOMETRY"
    if name[0].isdigit():
        name = f"L_{name}"
    return name[:255]


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _shape_z_values(shape: Any) -> list[float]:
    values = getattr(shape, "z", None)
    if values is None:
        return [0.0] * len(shape.points)
    return [_finite(value) for value in values]


def _parts(shape: Any) -> Iterable[list[tuple[float, float, float]]]:
    starts = list(shape.parts) + [len(shape.points)]
    z_values = _shape_z_values(shape)
    for start, end in zip(starts[:-1], starts[1:], strict=True):
        yield [
            (_finite(point[0]), _finite(point[1]), z)
            for point, z in zip(shape.points[start:end], z_values[start:end], strict=True)
        ]


def _extents(reader: Any) -> tuple[float, float, float, float, float, float]:
    min_x, min_y, max_x, max_y = [float(value) for value in reader.bbox]
    zbox = getattr(reader, "zbox", None)
    if zbox and len(zbox) == 2 and all(math.isfinite(float(value)) for value in zbox):
        min_z, max_z = [float(value) for value in zbox]
    else:
        min_z = max_z = 0.0
    return min_x, min_y, min_z, max_x, max_y, max_z


def _field_index(reader: Any, field_name: str | None) -> int | None:
    if not field_name:
        return None
    fields = [field[0] for field in reader.fields[1:]]
    lowered = [field.lower() for field in fields]
    target = field_name.lower()
    if target not in lowered:
        raise ValueError(f"Label field {field_name!r} not found; fields: {fields}")
    return lowered.index(target)


def _add_layers(document: Any, layers: list[str]) -> None:
    for layer in layers:
        if layer not in document.layers:
            document.layers.add(layer, color=7, linetype="CONTINUOUS")


def _add_polyline(modelspace: Any, layer: str, vertices: list[tuple[float, float, float]], closed: bool) -> bool:
    if len(vertices) < 2:
        return False
    if closed and len(vertices) > 2 and vertices[0] == vertices[-1]:
        vertices = vertices[:-1]
    modelspace.add_polyline3d(vertices, close=closed, dxfattribs={"layer": layer})
    return True


def export_dxf(
    input_path: Path,
    output_path: Path,
    encoding: str,
    layer: str | None,
    label_field: str | None,
    label_height: float,
    overwrite: bool,
    shapefile: Any,
    ezdxf: Any,
) -> dict[str, Any]:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output_path}; pass --overwrite to replace it")
    source_prj = input_path.with_suffix(".prj")
    output_prj = output_path.with_suffix(".prj")
    if (
        source_prj.exists()
        and source_prj.resolve() != output_prj.resolve()
        and output_prj.exists()
        and not overwrite
    ):
        raise FileExistsError(
            f"Output CRS sidecar exists: {output_prj}; pass --overwrite to replace it"
        )
    if label_height <= 0:
        raise ValueError("Label height must be greater than zero")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        reader = shapefile.Reader(str(input_path), encoding=encoding)
    except (OSError, shapefile.ShapefileException) as exc:
        raise ValueError(f"Unable to read Shapefile: {input_path}") from exc
    if len(reader) == 0:
        raise ValueError("Input Shapefile has no records")
    if reader.shapeType not in POINT_TYPES | POLYLINE_TYPES | POLYGON_TYPES | MULTIPOINT_TYPES:
        raise ValueError(f"Unsupported Shapefile geometry type: {reader.shapeTypeName}")

    geometry_layer = _layer_name(layer or input_path.stem)
    label_layer = _layer_name(f"{geometry_layer}_LABEL")
    label_index = _field_index(reader, label_field)
    if label_index is not None and reader.shapeType not in POINT_TYPES:
        raise ValueError("--label-field is currently supported only for point Shapefiles")
    layers = [geometry_layer] + ([label_layer] if label_index is not None else [])

    document = ezdxf.new("R2000")
    document.units = ezdxf.units.M
    min_x, min_y, min_z, max_x, max_y, max_z = _extents(reader)
    document.header["$EXTMIN"] = (min_x, min_y, min_z)
    document.header["$EXTMAX"] = (max_x, max_y, max_z)
    _add_layers(document, layers)
    modelspace = document.modelspace()

    entity_count = 0
    label_count = 0
    null_shape_count = 0
    for shape_record in reader.iterShapeRecords():
        shape = shape_record.shape
        if shape.shapeType == 0:
            null_shape_count += 1
            continue
        if shape.shapeType in POINT_TYPES:
            if not shape.points:
                raise ValueError("Point Shapefile contains a shape without coordinates")
            x, y = [_finite(value) for value in shape.points[0][:2]]
            z_values = _shape_z_values(shape)
            z = z_values[0] if z_values else 0.0
            modelspace.add_point((x, y, z), dxfattribs={"layer": geometry_layer})
            entity_count += 1
            if label_index is not None:
                text = modelspace.add_text(
                    str(shape_record.record[label_index]),
                    height=label_height,
                    dxfattribs={"layer": label_layer},
                )
                text.set_placement((x, y, z))
                label_count += 1
        elif shape.shapeType in MULTIPOINT_TYPES:
            z_values = _shape_z_values(shape)
            for point, z in zip(shape.points, z_values, strict=True):
                modelspace.add_point(
                    (_finite(point[0]), _finite(point[1]), z),
                    dxfattribs={"layer": geometry_layer},
                )
                entity_count += 1
        else:
            closed = shape.shapeType in POLYGON_TYPES
            for vertices in _parts(shape):
                if _add_polyline(modelspace, geometry_layer, vertices, closed):
                    entity_count += 1
    with tempfile.TemporaryDirectory(
        prefix=".shapefile-to-dxf-",
        dir=output_path.parent,
    ) as temp_name:
        staged_output = Path(temp_name) / output_path.name
        document.saveas(staged_output)
        saved_document = ezdxf.readfile(staged_output)
        auditor = saved_document.audit()
        saved_entity_count = len(list(saved_document.modelspace()))
        expected_entity_count = entity_count + label_count
        if auditor.errors or auditor.fixes or saved_entity_count != expected_entity_count:
            raise RuntimeError(
                "Generated DXF validation failed: "
                f"audit_errors={len(auditor.errors)}, audit_fixes={len(auditor.fixes)}, "
                f"entities={saved_entity_count}, expected={expected_entity_count}"
            )
        os.replace(staged_output, output_path)

    if source_prj.exists() and source_prj.resolve() != output_prj.resolve():
        shutil.copy2(source_prj, output_prj)
    reader.close()

    return {
        "source": str(input_path.resolve()),
        "output": str(output_path.resolve()),
        "sourceShapeType": reader.shapeTypeName,
        "sourceRecords": len(reader),
        "cadEntities": entity_count,
        "labels": label_count,
        "skippedNullShapes": null_shape_count,
        "layers": layers,
        "bbox": [float(value) for value in reader.bbox],
        "zRange": (
            [float(value) for value in reader.zbox]
            if getattr(reader, "zbox", None) is not None
            else None
        ),
        "units": "metres (DXF INSUNITS=6)",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export basic Shapefile geometries to AutoCAD 2000 DXF.")
    parser.add_argument("input", type=Path, help="Input .shp file")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--encoding", default="utf-8", help="DBF encoding (default: utf-8)")
    parser.add_argument("--layer", help="CAD layer name; defaults to the Shapefile basename")
    parser.add_argument("--label-field", help="Optional DBF field to export as TEXT for point layers")
    parser.add_argument("--label-height", type=float, default=2.5)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        shapefile, ezdxf = _load_dependencies()
        input_path = args.input.resolve()
        output_path = (args.output or input_path.with_suffix(".dxf")).resolve()
        if not input_path.is_file():
            raise ValueError(f"Input file not found: {input_path}")
        if input_path.suffix.lower() != ".shp":
            raise ValueError("Input must be a .shp file")
        if output_path.suffix.lower() != ".dxf":
            raise ValueError("Output must be a .dxf file")
        summary = export_dxf(
            input_path,
            output_path,
            args.encoding,
            args.layer,
            args.label_field,
            args.label_height,
            args.overwrite,
            shapefile,
            ezdxf,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUTPUT: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
