#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
坐标系转换命令行入口

在 WGS84 / GCJ02 / BD09 之间批量转换坐标。

两种模式：
- 点模式：坐标来自命令行参数、纯文本文件或标准输入，输出 text / CSV / JSON。
- 文件模式：传入结构化坐标文件（CSV / TSV / GeoJSON / GPX / KML），按扩展名
  自动识别格式，转换后写回同格式文件并保留其余结构（表头、其它列、
  properties、轨迹层级等）。

用法示例：
    # 点模式 - 单点：WGS84 -> GCJ02（默认输入顺序 lon,lat）
    python3 convert.py -f wgs84 -t gcj02 116.3974,39.9093

    # 点模式 - 多点：GCJ02 -> BD09
    python3 convert.py -f gcj02 -t bd09 116.40,39.91 117.0,30.5

    # 点模式 - 管道输入（每行一个 "lon,lat"）
    echo "116.40,39.91" | python3 convert.py -f wgs84 -t bd09

    # 文件模式 - CSV 表格（自动识别经纬度列），输出 points.gcj02.csv
    python3 convert.py -f wgs84 -t gcj02 -i points.csv

    # 文件模式 - GeoJSON / GPX / KML，按扩展名自动识别
    python3 convert.py -f wgs84 -t gcj02 -i track.gpx -o track_gcj02.gpx

坐标系标识支持常见别名：wgs84/gps、gcj02/高德/google、bd09/百度。
依赖：仅标准库。核心算法见 coordinate_converter.py，文件解析见 formats.py。
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coordinate_converter import (  # noqa: E402
    CoordinateConverter,
    normalize_system,
)
from formats import (  # noqa: E402
    FILE_FORMATS,
    detect_format,
    transform_file,
)


def _parse_point(token: str, lat_first: bool) -> tuple[float, float]:
    """将一个 "a,b" 文本解析为 (lon, lat)。

    分隔符兼容逗号、空白与中文逗号；``lat_first`` 为真时输入按 lat,lon 解析。
    """
    cleaned = token.replace("，", ",").replace("\t", " ")
    parts = [p for p in cleaned.replace(",", " ").split() if p]
    if len(parts) != 2:
        raise ValueError(f"无法解析坐标 {token!r}，应为 'lon,lat' 形式的两个数字")
    a, b = float(parts[0]), float(parts[1])
    return (b, a) if lat_first else (a, b)


def _collect_tokens(args: argparse.Namespace) -> list[str]:
    """按优先级收集待转换的坐标文本：命令行参数 > 输入文件 > 标准输入。"""
    if args.coords:
        return list(args.coords)
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def _format_results(rows: list[tuple[float, float]], fmt: str,
                    precision: int, lat_first: bool) -> str:
    """将转换结果渲染为指定格式（text / csv / json）。"""
    def order(lon: float, lat: float) -> tuple[float, float]:
        return (round(lat, precision), round(lon, precision)) if lat_first \
            else (round(lon, precision), round(lat, precision))

    if fmt == "json":
        data = [{"lon": round(lon, precision), "lat": round(lat, precision)}
                for lon, lat in rows]
        return json.dumps(data, ensure_ascii=False, indent=2)

    sep = "," if fmt == "csv" else ", "
    lines = [f"{order(lon, lat)[0]}{sep}{order(lon, lat)[1]}"
             for lon, lat in rows]
    return "\n".join(lines)


def _run_file_mode(args: argparse.Namespace, src_key: str, dst_key: str,
                   fmt: str) -> int:
    """处理结构化坐标文件（CSV/TSV/GeoJSON/GPX/KML），写回同格式并返回退出码。"""
    def transform(lon: float, lat: float) -> tuple[float, float]:
        out_lon, out_lat = CoordinateConverter.convert(lon, lat,
                                                       src_key, dst_key)
        return (round(out_lon, args.precision), round(out_lat, args.precision))

    in_path = Path(args.input)
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = in_path.with_suffix(f".{dst_key}{in_path.suffix}")

    try:
        count = transform_file(in_path, out_path, fmt, transform,
                               lon_col=args.lon_col, lat_col=args.lat_col)
    except (ValueError, KeyError, IndexError) as exc:
        print(f"错误：解析 {fmt.upper()} 文件失败：{exc}", file=sys.stderr)
        return 1

    print(f"已转换 {count} 个坐标（{src_key} -> {dst_key}）", file=sys.stderr)
    print(f"OUTPUT: {out_path.resolve()}", file=sys.stderr)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    """解析参数、执行批量坐标转换并输出结果。返回退出码。"""
    parser = argparse.ArgumentParser(
        description="在 WGS84 / GCJ02 / BD09 之间批量转换坐标。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("coords", nargs="*",
                        help="坐标，形如 'lon,lat'，可给多个；省略则读取 --input 或标准输入")
    parser.add_argument("-f", "--from", dest="src", required=True,
                        help="源坐标系：wgs84 / gcj02 / bd09（含别名）")
    parser.add_argument("-t", "--to", dest="dst", required=True,
                        help="目标坐标系：wgs84 / gcj02 / bd09（含别名）")
    parser.add_argument("-i", "--input",
                        help="输入文件：纯文本（每行 'lon,lat'）或结构化坐标文件"
                             "（CSV/TSV/GeoJSON/GPX/KML，按扩展名识别）")
    parser.add_argument("-o", "--output",
                        help="输出文件路径，省略则打印到标准输出（文件模式默认写到"
                             " <输入名>.<目标坐标系>.<扩展名>）")
    parser.add_argument("--in-format", choices=FILE_FORMATS, dest="in_format",
                        help="强制指定输入文件格式，覆盖扩展名自动识别")
    parser.add_argument("--lon-col",
                        help="CSV/TSV 经度列名或 0 起始序号（省略则自动识别）")
    parser.add_argument("--lat-col",
                        help="CSV/TSV 纬度列名或 0 起始序号（省略则自动识别）")
    parser.add_argument("--lat-first", action="store_true",
                        help="点模式输入/输出按 lat,lon 顺序（默认 lon,lat）")
    parser.add_argument("--format", choices=("text", "csv", "json"),
                        default="text", help="点模式输出格式（默认 text）")
    parser.add_argument("--precision", type=int, default=6,
                        help="结果保留小数位数（默认 6）")
    args = parser.parse_args(argv)

    # 先校验坐标系标识，错误参数在产生任何副作用前即报错退出
    try:
        src_key = normalize_system(args.src)
        dst_key = normalize_system(args.dst)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2

    # 文件模式：输入是可识别的结构化坐标文件
    if args.input:
        fmt = detect_format(args.input, args.in_format)
        if fmt in FILE_FORMATS:
            return _run_file_mode(args, src_key, dst_key, fmt)

    tokens = _collect_tokens(args)
    if not tokens:
        print("错误：未提供任何坐标（命令行参数、--input 或标准输入均为空）",
              file=sys.stderr)
        return 2

    rows: list[tuple[float, float]] = []
    for token in tokens:
        try:
            lon, lat = _parse_point(token, args.lat_first)
        except ValueError as exc:
            print(f"错误：{exc}", file=sys.stderr)
            return 1
        rows.append(CoordinateConverter.convert(lon, lat, src_key, dst_key))

    output = _format_results(rows, args.format, args.precision, args.lat_first)

    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
        print(f"OUTPUT: {Path(args.output).resolve()}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
