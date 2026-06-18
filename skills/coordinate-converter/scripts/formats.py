#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化坐标文件的解析与原地改写

为 convert.py 提供「读入结构化坐标文件 -> 对每个坐标应用变换 -> 按原格式写回」的
能力，保留文件的其余结构（表头、其它列、properties、轨迹层级、样式等）。

支持格式：
- CSV / TSV 表格（自动或手动指定经纬度列）
- GeoJSON（.geojson / .json，遍历所有 geometry 的 coordinates）
- GPX（.gpx，wpt / trkpt / rtept 的 lat、lon 属性）
- KML（.kml，Placemark 的 coordinates 文本）

依赖：仅标准库（csv、json、xml.etree、re）。命令行入口见同目录 convert.py。
"""

from __future__ import annotations

import re
import csv
import json
import xml.etree.ElementTree as ET
from io import StringIO
from typing import Callable
from pathlib import Path

# 变换函数签名：接收 (lon, lat)，返回变换后的 (lon, lat)
Transform = Callable[[float, float], "tuple[float, float]"]

# 支持的文件格式与扩展名映射
_EXT_TO_FORMAT = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".geojson": "geojson",
    ".json": "geojson",
    ".gpx": "gpx",
    ".kml": "kml",
}
FILE_FORMATS = ("csv", "tsv", "geojson", "gpx", "kml")

# CSV 表头中常见的经纬度列名（小写匹配）
_LON_NAMES = {"lon", "lng", "long", "longitude", "经度", "x"}
_LAT_NAMES = {"lat", "latitude", "纬度", "y"}


def detect_format(path: str | Path, override: str | None = None) -> str | None:
    """根据 ``override`` 或文件扩展名判定格式，无法识别返回 ``None``。"""
    if override:
        return override
    return _EXT_TO_FORMAT.get(Path(path).suffix.lower())


def transform_file(in_path: str | Path, out_path: str | Path, fmt: str,
                   transform: Transform, *, lon_col: str | None = None,
                   lat_col: str | None = None) -> int:
    """读入 ``in_path``，对每个坐标应用 ``transform``，按 ``fmt`` 写回 ``out_path``。

    返回成功转换的坐标点数量。``lon_col`` / ``lat_col`` 仅对 CSV/TSV 生效，
    可为列名或 0 起始的列序号；省略时自动识别。
    """
    text = Path(in_path).read_text(encoding="utf-8")
    if fmt in ("csv", "tsv"):
        delimiter = "\t" if fmt == "tsv" else ","
        output, count = _transform_table(text, transform, delimiter,
                                          lon_col, lat_col)
    elif fmt == "geojson":
        output, count = _transform_geojson(text, transform)
    elif fmt == "gpx":
        output, count = _transform_gpx(text, transform)
    elif fmt == "kml":
        output, count = _transform_kml(text, transform)
    else:
        raise ValueError(f"不支持的文件格式: {fmt!r}")
    Path(out_path).write_text(output, encoding="utf-8")
    return count


def _resolve_column(spec: str, header: list[str], names: set[str],
                    kind: str) -> int:
    """把列名/列序号解析为列索引。

    ``spec`` 为 None 时按 ``names`` 在表头中自动识别；为数字时当作 0 起始序号；
    否则当作列名（大小写不敏感）。
    """
    if spec is None:
        for idx, name in enumerate(header):
            if name.strip().lower() in names:
                return idx
        raise ValueError(
            f"无法在表头中自动识别{kind}列，请用 --{kind}-col 指定列名或序号；"
            f"当前表头：{header}")
    if spec.lstrip("-").isdigit():
        idx = int(spec)
        if not 0 <= idx < len(header):
            raise ValueError(f"{kind}列序号 {idx} 超出范围（共 {len(header)} 列）")
        return idx
    lowered = [h.strip().lower() for h in header]
    target = spec.strip().lower()
    if target in lowered:
        return lowered.index(target)
    raise ValueError(f"表头中找不到{kind}列 {spec!r}；当前表头：{header}")


def _transform_table(text: str, transform: Transform, delimiter: str,
                     lon_col: str | None, lat_col: str | None
                     ) -> tuple[str, int]:
    """转换 CSV/TSV 表格，就地替换经纬度列，保留其余列与表头。"""
    rows = list(csv.reader(StringIO(text), delimiter=delimiter))
    if not rows:
        return ("", 0)
    header = rows[0]
    lon_idx = _resolve_column(lon_col, header, _LON_NAMES, "lon")
    lat_idx = _resolve_column(lat_col, header, _LAT_NAMES, "lat")

    count = 0
    for row in rows[1:]:
        if len(row) <= max(lon_idx, lat_idx) or not row[lon_idx].strip():
            continue
        lon, lat = float(row[lon_idx]), float(row[lat_idx])
        row[lon_idx], row[lat_idx] = (str(v) for v in transform(lon, lat))
        count += 1

    buf = StringIO()
    csv.writer(buf, delimiter=delimiter, lineterminator="\n").writerows(rows)
    return (buf.getvalue(), count)


def _transform_position_tree(node: object, transform: Transform,
                             counter: list[int]) -> object:
    """递归处理 GeoJSON 的 coordinates 子树，对每个 [lon, lat(, alt)] 位置变换。"""
    if (isinstance(node, list) and len(node) >= 2
            and all(isinstance(v, (int, float)) for v in node[:2])):
        lon, lat = transform(node[0], node[1])
        counter[0] += 1
        return [lon, lat, *node[2:]]
    if isinstance(node, list):
        return [_transform_position_tree(c, transform, counter) for c in node]
    return node


def _transform_geojson(text: str, transform: Transform) -> tuple[str, int]:
    """转换 GeoJSON 中所有 geometry 的 coordinates，保留 properties 等结构。"""
    data = json.loads(text)
    counter = [0]

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "coordinates":
                    obj[key] = _transform_position_tree(value, transform,
                                                        counter)
                else:
                    walk(value)
        elif isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(data)
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n", counter[0])


def _localname(tag: str) -> str:
    """去掉 XML 标签的命名空间前缀，返回本地名。"""
    return tag.split("}")[-1]


def _register_root_namespace(text: str) -> None:
    """把根元素默认命名空间注册为空前缀，避免写回时出现 ns0: 前缀。"""
    match = re.search(r'xmlns="([^"]+)"', text)
    if match:
        ET.register_namespace("", match.group(1))


def _serialize_xml(root: ET.Element) -> str:
    """序列化 XML 元素树，带 UTF-8 声明与结尾换行。"""
    body = ET.tostring(root, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"


def _transform_gpx(text: str, transform: Transform) -> tuple[str, int]:
    """转换 GPX 中所有带 lat/lon 属性的元素（wpt / trkpt / rtept）。"""
    _register_root_namespace(text)
    root = ET.fromstring(text)
    count = 0
    for elem in root.iter():
        if "lat" in elem.attrib and "lon" in elem.attrib:
            lon, lat = transform(float(elem.attrib["lon"]),
                                 float(elem.attrib["lat"]))
            elem.attrib["lon"], elem.attrib["lat"] = str(lon), str(lat)
            count += 1
    return (_serialize_xml(root), count)


def _transform_kml(text: str, transform: Transform) -> tuple[str, int]:
    """转换 KML 中所有 <coordinates> 元素文本（lon,lat[,alt] 空白分隔）。"""
    _register_root_namespace(text)
    root = ET.fromstring(text)
    count = 0
    for elem in root.iter():
        if _localname(elem.tag) != "coordinates" or not elem.text:
            continue
        converted = []
        for tuple_text in elem.text.split():
            parts = tuple_text.split(",")
            lon, lat = transform(float(parts[0]), float(parts[1]))
            converted.append(",".join(str(v) for v in (lon, lat, *parts[2:])))
            count += 1
        # 保留原有缩进风格：单点内联，多点逐行
        if len(converted) == 1:
            elem.text = converted[0]
        else:
            elem.text = "\n" + "\n".join(converted) + "\n"
    return (_serialize_xml(root), count)
