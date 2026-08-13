---
name: geospatial-converter
description: >
  统一处理地理空间坐标与文件格式转换：在 WGS84、GCJ02（高德/腾讯）和
  BD09（百度）之间转换经纬度；把含 X/Y/Z 坐标的 XLSX、CSV 或 TSV
  表格生成 Point/PointZ Shapefile；把 Shapefile 导出为 DXF 或 DWG，并通过 ODA
  回转审计验证可交付 DWG；识别并安全处理投影坐标、地方独立坐标和工程坐标
  （如成都坐标系），保留属性、生成 PRJ/CPG，并校验要素数、坐标范围与高程。
  支持把截图作为 GroundOverlay 贴合到 KML 面并打包为 KMZ。当用户要求坐标
  纠偏、坐标系判断、坐标表转 SHP、SHP 转 CAD/DWG、截图叠加到 KML 面，
  或询问数据能否导入地图时使用。
---

# 地理空间数据转换

用同一套流程处理 Web 地图坐标、坐标表、Shapefile 和 CAD 文件。先确认几何、字段和坐标参考，再执行转换并验证输出。

## 安全边界

- 不根据数值范围擅自判定唯一坐标系，也不自动给 X/Y 补高斯带号。
- “成都坐标系”等地方独立坐标可原值写入 SHP/DXF/DWG，并用 `LOCAL_CS` 标注来源；这不等于已获得到 CGCS2000、WGS84 或在线底图的转换关系。
- 只有取得正式 EPSG/PRJ、中央经线与带号、转换参数或公共控制点后，才执行地方坐标与国家坐标之间的转换。
- 同一地方坐标系的数据可直接叠加；要与在线底图或其他坐标系叠加，必须先完成可靠配准。
- 需要判断投影坐标或地方坐标时，先读 [references/projected-and-local-crs.md](references/projected-and-local-crs.md)。

## 工作流路由

| 任务 | 工具 | 说明 |
|---|---|---|
| WGS84 / GCJ02 / BD09 互转 | `scripts/convert.py` | 支持单点、列表及 CSV/TSV/GeoJSON/GPX/KML |
| XLSX/CSV 坐标表转 SHP | `scripts/tabular_to_shapefile.py` | 输出包含 SHP/SHX/DBF/PRJ/CPG、字段映射和报告的 ZIP |
| SHP 转 DXF | `scripts/shapefile_to_dxf.py` | 支持点、线、面和多点，保留 Z；可按字段生成文字标注 |
| DXF 转 DWG | `scripts/dxf_to_dwg.py` | 默认调用 ODA File Converter，并强制执行 DWG→DXF 回转审计 |
| 截图叠加到 KML 面 | `scripts/kml_image_overlay.py` | 选择目标面并输出内嵌图片的便携 KMZ |

表格和 Shapefile 工具需要安装依赖：

```bash
python3 -m pip install -r resources/requirements.txt
```

## 坐标表生成 Shapefile

先检查工作表名称、X/Y/Z 列、记录数和坐标范围。地方坐标只需标注名称，不做未经证实的数值变换：

```bash
python3 scripts/tabular_to_shapefile.py input.xlsx \
  --sheet Sheet1 \
  --x-col X --y-col Y --z-col High \
  --local-crs-name "Chengdu City Coordinate System" \
  -o output_shapefile.zip
```

已取得正式 `.prj` 时，改用：

```bash
python3 scripts/tabular_to_shapefile.py input.csv \
  --x-col Easting --y-col Northing --z-col Elevation \
  --prj-file authoritative.prj \
  -o output_shapefile.zip
```

已确认 EPSG 编号时也可以直接生成标准 `.prj`：

```bash
python3 scripts/tabular_to_shapefile.py input.csv \
  --x-col 经度 --y-col 纬度 \
  --epsg 4326 \
  -o output_shapefile.zip
```

`--epsg`、`--prj-file` 和 `--local-crs-name` 必须且只能选择一个。默认遇到无效坐标即停止；确认允许丢弃异常行后才使用 `--skip-invalid`。输出 ZIP 内包含字段名映射 CSV 和转换报告 JSON，用于追溯 DBF 的 10 字符字段名限制。

## Shapefile 导出 DXF / DWG

先解压完整 Shapefile 组件，再生成 DXF：

```bash
python3 scripts/shapefile_to_dxf.py input.shp \
  --layer SURVEY_POINT \
  --label-field PointName \
  -o output.dxf
```

DWG 不是纯 Python 原生格式。可交付 DWG 必须由 ODA File Converter 生成；脚本会启用 ODA 审计，把生成的 DWG 反向转换为 DXF，再比较实体类型、图层、三维范围并执行 `ezdxf` 审计。任一检查失败都不会替换目标文件：

ODA File Converter 需从 [Open Design Alliance 官方页面](https://www.opendesign.com/GUESTFILES/ODA_FILE_CONVERTER)单独安装。

```bash
# 自动查找 ODAFileConverter；不会自动回退到 LibreDWG
python3 scripts/dxf_to_dwg.py output.dxf -o output.dwg \
  --report output_validation.json

# 明确指定命令行程序；macOS 也可以直接指定 .app 包
python3 scripts/dxf_to_dwg.py output.dxf -o output.dwg \
  --converter oda --converter-path /path/to/ODAFileConverter \
  --version r2000 --report output_validation.json
```

只有明确接受兼容性风险、且仅用于内部实验时，才可以显式传入 `--converter libredwg`。这种输出会标记为 `experimental-not-for-delivery`，不能仅凭 LibreDWG 自身能够读回就对外交付。

SHP 的完整业务属性保留在 DBF 中；DXF/DWG 主要承载几何和可选文字标注。脚本会复制同名 `.prj` 边车文件，但 CAD 文件本身通常不会完整表达 GIS 坐标参考。

## 截图叠加到 KML 面

KML 中只有一个面时可直接执行：

```bash
python3 scripts/kml_image_overlay.py area.kml screenshot.png \
  -o area_overlay.kmz
```

多个面时按 Placemark 名称或从 1 开始的序号选择：

```bash
python3 scripts/kml_image_overlay.py area.kml screenshot.jpg \
  --polygon-name "目标区域" --opacity 0.85 \
  -o area_overlay.kmz
```

凸四边形且四角方向可唯一判断时，默认用 `gx:LatLonQuad` 精确贴合；方向有歧义或不是凸四边形时，自动使用透明裁剪。需要最大 KML 软件兼容性时传入 `--mode clip`。处理前读取 [references/kml-image-overlays.md](references/kml-image-overlays.md)，确认面为 WGS84 经纬度且截图方向为上北下南。

## Web 地图坐标转换

支持以下标识：

| 标识 | 常用别名 | 用途 |
|---|---|---|
| `wgs84` | `gps`、`wgs` | GPS / 国际经纬度 |
| `gcj02` | `高德`、`腾讯`、`火星` | 中国大陆 Web 地图偏移坐标 |
| `bd09` | `百度`、`bd` | 百度地图坐标 |

```bash
# 单点，默认 lon,lat
python3 scripts/convert.py -f wgs84 -t gcj02 116.3974,39.9093

# 文件模式，自动识别 CSV 经纬度列并保留其余字段
python3 scripts/convert.py -f wgs84 -t bd09 -i points.csv -o points_bd09.csv

# 手动指定列名
python3 scripts/convert.py -f 高德 -t wgs84 -i points.tsv \
  --lon-col 经度 --lat-col 纬度
```

文件模式支持 CSV、TSV、GeoJSON、GPX 和 KML；点模式支持 `--lat-first`、`--format text|csv|json` 和 `--precision`。核心算法位于 `scripts/coordinate_converter.py`，只依赖标准库。

## 验证清单

交付前至少核对：

1. 输出要素数与有效输入行数一致；若跳过异常行，报告中有明确计数。
2. X/Y 最小值、最大值与源数据一致；PointZ 的 Z 范围和空值策略符合预期。
3. SHP 能重新读取，且 `.shp`、`.shx`、`.dbf`、`.prj`、`.cpg` 齐全。
4. 可交付 DWG 的验证报告必须为 `deliveryStatus: validated`，并通过 ODA 回转审计、实体类型、图层和三维包围盒比较；只有 DWG 文件头正确不算验证通过。
5. 明确告知用户：数据是“已保留地方坐标”还是“已转换到可与地图叠加的标准坐标”。
