---
name: coordinate-converter
description: >
  在 WGS84（GPS / 国际标准）、GCJ02（火星坐标 / 高德 / 谷歌中国 / 腾讯）、
  BD09（百度地图）三种中国常用坐标系之间相互转换经纬度。支持单点、一系列坐标，
  也支持直接处理常用坐标文件（CSV / TSV / GeoJSON / GPX / KML），按格式原样写回
  并保留其余结构。当用户给出一个或一批经纬度、或一个坐标文件并要求换算坐标系时使用，
  例如「WGS84 转高德」「百度坐标转 GPS」「批量把这些坐标转成 GCJ02」「火星坐标纠偏」
  「把这个 csv/geojson/gpx/kml 的坐标转成另一个坐标系」。
---

# 坐标系转换

在三种中国常用坐标系之间换算经纬度：

| 标识 | 别名 | 用途 |
|---|---|---|
| `wgs84` | `gps`、`wgs` | 国际标准 GPS 坐标 |
| `gcj02` | `高德`、`google`、`腾讯`、`火星` | 国测局加密坐标（高德、谷歌中国、腾讯地图） |
| `bd09` | `百度`、`bd` | 百度地图坐标 |

任意两种坐标系可直接互转；非中国境内坐标自动跳过 GCJ02 偏移。

## 快速开始

```bash
# 单点：WGS84 -> GCJ02（默认输入顺序 lon,lat）
python3 scripts/convert.py -f wgs84 -t gcj02 116.3974,39.9093

# 多点：一次给多个坐标
python3 scripts/convert.py -f gcj02 -t bd09 116.40,39.91 117.0,30.5

# 使用别名（中文/平台名）
python3 scripts/convert.py -f 高德 -t 百度 116.40,39.91
```

转换结果默认打印到标准输出。

## 两种模式

**点模式**——零散坐标，灵活输出（优先级：参数 > 文件 > 标准输入）：

```bash
# 命令行参数
python3 scripts/convert.py -f wgs84 -t bd09 116.40,39.91 117.0,30.5

# 纯文本文件：每行一个 "lon,lat"
python3 scripts/convert.py -f wgs84 -t gcj02 -i points.txt

# 管道 / 标准输入
echo "116.40,39.91" | python3 scripts/convert.py -f wgs84 -t bd09
```

分隔符兼容英文逗号、中文逗号与空白，所以 `116.40,39.91`、`116.40, 39.91`、`116.40 39.91` 都可解析。

**文件模式**——结构化坐标文件，按扩展名自动识别，转换后写回**同格式**并保留其余结构：

| 格式 | 扩展名 | 转换范围 | 保留内容 |
|---|---|---|---|
| CSV / TSV | `.csv` `.tsv` | 自动识别（或指定）经纬度列 | 表头、其它所有列 |
| GeoJSON | `.geojson` `.json` | 所有 geometry 的 coordinates | properties、几何类型、嵌套层级 |
| GPX | `.gpx` | `wpt` / `trkpt` / `rtept` 的 lat、lon | 轨迹层级、名称、其它标签 |
| KML | `.kml` | 所有 `<coordinates>` | Placemark、样式、高程值 |

```bash
# CSV 表格：自动识别 lon/lng/经度 与 lat/纬度 列，输出 points.gcj02.csv
python3 scripts/convert.py -f wgs84 -t gcj02 -i points.csv

# 手动指定经纬度列（列名或 0 起始序号）
python3 scripts/convert.py -f wgs84 -t bd09 -i data.csv --lon-col 经度 --lat-col 纬度

# GeoJSON / GPX / KML
python3 scripts/convert.py -f wgs84 -t gcj02 -i track.gpx -o track_gcj02.gpx

# 无扩展名时用 --in-format 强制指定
python3 scripts/convert.py -f wgs84 -t gcj02 -i data --in-format geojson
```

文件模式下 `-o` 省略时默认写到 `<输入名>.<目标坐标系>.<扩展名>`（如 `points.gcj02.csv`），并在标准错误打印转换点数与 `OUTPUT:` 绝对路径。

## 选项

| 选项 | 说明 |
|---|---|
| `-f` / `--from` | 源坐标系（必填） |
| `-t` / `--to` | 目标坐标系（必填） |
| `-i` / `--input` | 输入文件：纯文本列表或结构化坐标文件（CSV/TSV/GeoJSON/GPX/KML） |
| `-o` / `--output` | 输出文件路径，省略则打印到标准输出（文件模式有默认命名） |
| `--in-format` | 强制指定输入文件格式，覆盖扩展名识别（`csv`/`tsv`/`geojson`/`gpx`/`kml`） |
| `--lon-col` | CSV/TSV 经度列名或 0 起始序号（省略则自动识别） |
| `--lat-col` | CSV/TSV 纬度列名或 0 起始序号（省略则自动识别） |
| `--lat-first` | 点模式输入与输出按 `lat,lon` 顺序（默认 `lon,lat`） |
| `--format` | 点模式输出格式：`text`（默认）/ `csv` / `json` |
| `--precision` | 结果保留小数位数（默认 6） |

```bash
# 纬度在前 + CSV 输出到文件
python3 scripts/convert.py -f bd09 -t wgs84 --lat-first --format csv \
    -i points.txt -o out.csv

# JSON 输出
python3 scripts/convert.py -f gcj02 -t wgs84 --format json 116.40,39.91
```

成功写入文件时会在标准错误打印 `OUTPUT: /绝对路径/out.csv`。

## 作为库使用

核心算法在 `scripts/coordinate_converter.py`，仅依赖标准库：

```python
from coordinate_converter import CoordinateConverter

# 具名方法
lon, lat = CoordinateConverter.wgs84_to_gcj02(116.3974, 39.9093)

# 动态分发（按字符串选择源/目标坐标系）
lon, lat = CoordinateConverter.convert(116.3974, 39.9093, "wgs84", "bd09")
```

## 说明

- 坐标顺序默认 **经度在前**（`lon,lat`），与多数 Web 地图 API 一致；GPS 设备/部分数据集是纬度在前，用 `--lat-first`。
- `gcj02_to_wgs84` 为单次近似纠偏，亚米级精度足够日常使用；如需更高精度可多次迭代。
- 中国境外坐标不做 GCJ02 偏移，原样返回。
