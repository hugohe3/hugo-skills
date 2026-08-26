---
name: wind-turbine-dwg-layout
description: >
  将机位坐标点 DWG 中的点位和编号批量标注到新的底图 DWG，使用内置的 IB 风机示意图、
  25×25 定位方框和 HD数字# 编号样式，并校验数量、坐标和源文件未被覆盖。当用户要求把
  风机点、机位坐标或调整后机位叠加到另一张 DWG，或要求沿用 IB 风机布置样式时使用。
---

# 风机 DWG 点位布置

将坐标点 DWG 中的机位批量写入一份新的底图副本。每个机位必须由三个独立对象组成：

1. `fj` 风机示意图块；
2. 风机下方的 25×25 小方框；
3. `HD数字#` 格式的编号，例如 `HD2#`。

## 输入要求

- `PointDwg`：包含 `POINT` 实体和对应数字文字的机位坐标文件。文字应与点重合或处于匹配容差内，且编号唯一。
- `BaseDwg`：待叠加的底图。底图必须和坐标点文件使用同一坐标系、同一单位。
- `OutputDwg`：新的输出路径，不得与任一输入文件相同，也不能是已存在文件。

不要自动猜测或执行坐标转换。如果两个 DWG 的坐标系、中央子午线或单位不一致，先停止并说明需要用户确认转换参数。

## 执行方式

要求 Windows 上已安装并打开 AutoCAD。运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/apply_wind_turbine_layout.ps1 `
  -PointDwg "C:/path/机位坐标.dwg" `
  -BaseDwg "C:/path/新底图.dwg" `
  -OutputDwg "C:/path/新底图_IB风机布置.dwg"
```

可选参数：

- `-LabelPrefix "HD"`：编号前缀，默认 `HD`。
- `-LabelSuffix "#"`：编号后缀，默认 `#`。
- `-MatchTolerance 0.5`：点与数字文字的最大匹配距离，默认 0.5 个图形单位。
- `-AllowTextOnly`：仅在源文件完全没有 `POINT` 时，允许直接使用数字文字插入点；默认不允许。

脚本成功时输出 JSON，且 `status` 必须为 `validated`。向用户交付前检查其中的对象数量和输入文件哈希校验结果。

## 内置标准样式

- `assets/ib-fj-template.dwg`：保留 `fj` 块的真实风机几何图形和依赖项。
- `assets/ib-label-template.dwg`：保留 `HZ` 文字样式、颜色和 MText 格式。
- `assets/ib-style.json`：记录风机图层、编号偏移和方框几何参数。

默认样式源自 `初步布置图1013.dwg`：

- `fj` 放在 `IB风机布置` 图层，插入点严格等于机位坐标；
- 方框放在 `mainlayer`，尺寸为 25×25，保留标准中心偏移、颜色和线宽；
- 编号放在 `mainlayer`，沿用模板 MText 格式，编号内容替换为 `HD数字#`。

## 质量门槛

只有同时满足以下条件，才能报告完成：

- 生成的 `fj`、方框和编号数量均等于有效机位数量；
- 每个 `fj` 插入点与源机位坐标一致；
- 每个方框尺寸均为 25×25，且样式参数与内置配置一致；
- 每个源编号恰好对应一个 `HD数字#` 编号；
- 两份输入 DWG 的 SHA-256 哈希在运行前后保持不变；
- 输出 DWG 已成功保存为新文件。

任一校验失败都应明确报错，不要把未验证的文件当作完成结果。失败清理只能删除本次运行刚创建的输出副本，不能删除或改写输入文件。
