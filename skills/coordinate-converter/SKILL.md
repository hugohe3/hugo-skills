---
name: coordinate-converter
description: >
  在 WGS84（GPS / 国际标准）、GCJ02（火星坐标 / 高德 / 谷歌中国 / 腾讯）、
  BD09（百度地图）三种中国常用坐标系之间相互转换经纬度。支持单点或一系列坐标，
  输入可来自参数、文件或标准输入，输出 text / CSV / JSON。当用户给出一个或一批
  经纬度并要求换算坐标系时使用，例如「WGS84 转高德」「百度坐标转 GPS」
  「批量把这些坐标转成 GCJ02」「火星坐标纠偏」。
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

## 输入方式（优先级：参数 > 文件 > 标准输入）

```bash
# 命令行参数
python3 scripts/convert.py -f wgs84 -t bd09 116.40,39.91 117.0,30.5

# 文件：每行一个 "lon,lat"
python3 scripts/convert.py -f wgs84 -t gcj02 -i points.txt

# 管道 / 标准输入
echo "116.40,39.91" | python3 scripts/convert.py -f wgs84 -t bd09
```

分隔符兼容英文逗号、中文逗号与空白，所以 `116.40,39.91`、`116.40, 39.91`、`116.40 39.91` 都可解析。

## 选项

| 选项 | 说明 |
|---|---|
| `-f` / `--from` | 源坐标系（必填） |
| `-t` / `--to` | 目标坐标系（必填） |
| `-i` / `--input` | 输入文件，每行一个 `lon,lat` |
| `-o` / `--output` | 输出文件路径，省略则打印到标准输出 |
| `--lat-first` | 输入与输出按 `lat,lon` 顺序（默认 `lon,lat`） |
| `--format` | 输出格式：`text`（默认）/ `csv` / `json` |
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
