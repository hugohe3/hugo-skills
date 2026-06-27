---
name: image-local-replacer
description: >
  对 PNG/JPG/WebP 等位图做小范围局部替换、局部遮盖、局部文字重写或局部修补。
  使用 Python/Pillow 基于矩形区域进行像素级覆盖、背景采样、颜色匹配和可选文字绘制，
  保持原图尺寸、文件名和未选中区域不变。适用于用户要求“只改这一小块”“不要整图 AI 重绘”
  “替换图片里的编号/标签/日期/小段文字”“遮盖局部内容”“修补局部残留像素”等场景。
---

# 图片局部替换

对已经固化在位图中的小范围内容做可控替换。优先使用确定性的局部像素编辑：读取原图，按配置只处理指定矩形区域，必要时从周边采样背景，再写入新内容或仅覆盖清除。

## 核心原则

- 只修改用户指定或校准后的局部区域。
- 不使用整图 AI 重绘，不重新生成整张图。
- 不改变图片宽高、文件名和未选中区域。
- 先输出到预览目录，确认无误后再覆盖原图。
- 对残留像素做二次修正时，只覆盖残留区域，不扩大影响范围。

## 适用场景

| 场景 | 推荐方式 |
|---|---|
| 替换图中编号、标签、日期、小段文字 | 覆盖旧文字区域，再按相近颜色、字号和字体写入新文字 |
| 遮盖局部敏感信息 | 用背景采样色、指定纯色或模糊前的近似色覆盖局部区域 |
| 清理旧字符残影、标注残留 | 用更小矩形做二次覆盖 |
| 修补地图、工程图、截图中的小块错误 | 只处理错误区域，保留线条、图例、边界、点位等其他内容 |

不适合：需要理解复杂语义、重建大面积背景、补全缺失物体、改变图像风格或生成新画面的任务；这些应使用专门图像编辑工作流，而不是本技能。

## 工作流

1. 收集目标图片路径和替换要求，明确哪些区域允许修改。
2. 预览图片，定位需要替换的最小矩形区域。矩形坐标使用 `[left, top, right, bottom]`。
3. 需要写新文字时，记录文字左上角 `[x, y]`、颜色、字号和字体；尽量匹配原图视觉风格。
4. 创建 JSON 配置，每个局部替换项只描述一个小区域。
5. 先运行脚本输出到预览目录，逐张检查。
6. 如存在残留、遮挡或颜色突兀，微调 `cover`、`background`、`padding`、`text_xy`、`font_size` 后重跑。
7. 确认无误后再使用 `--overwrite` 覆盖原图。

## 配置示例

坐标均为像素坐标：

```json
{
  "default": {
    "font_size": 24,
    "fill": "#d71920",
    "stroke_width": 0
  },
  "items": [
    {
      "file": "map.png",
      "description": "替换左上角机位编号",
      "cover": [100, 120, 158, 148],
      "text": "XD1",
      "text_xy": [102, 116]
    },
    {
      "file": "screenshot.png",
      "description": "遮盖手机号",
      "cover": [320, 88, 460, 116],
      "background": "#ffffff"
    }
  ]
}
```

字段说明：

| 字段 | 必填 | 说明 |
|---|---|---|
| `file` | 是 | 相对输入目录的图片路径 |
| `cover` | 是 | 要覆盖的局部矩形 `[left, top, right, bottom]` |
| `description` | 否 | 人工复核说明，不参与绘制 |
| `text` | 否 | 覆盖后写入的新文字；不填则只做局部覆盖 |
| `text_xy` | 写文字时必填 | 新文字左上角 `[x, y]` |
| `font_size` | 否 | 字号，未设置时使用 `default.font_size` |
| `font` | 否 | 字体文件路径，未设置时尝试常见系统字体 |
| `fill` | 否 | 文字颜色，支持 `#RRGGBB` 或 `[r,g,b]` |
| `background` | 否 | 覆盖色；未设置时脚本从覆盖框周围采样中位数颜色 |
| `padding` | 否 | 覆盖框额外扩张像素，默认 `0` |
| `stroke_width` | 否 | 文字描边宽度，默认 `0` |
| `stroke_fill` | 否 | 文字描边颜色 |

## 运行方式

安装依赖：

```bash
pip install -r resources/requirements.txt
```

先输出到检查目录：

```bash
python3 scripts/apply_local_replacements.py ./images replacements.json -o ./preview-images
```

检查无误后覆盖原文件：

```bash
python3 scripts/apply_local_replacements.py ./images replacements.json --overwrite
```

如果需要辅助定位红色文字或红色标注，可生成红色像素遮罩：

```bash
python3 scripts/apply_local_replacements.py ./images replacements.json --red-mask-dir ./red-mask
```

## 验收

- 输出图与原图宽高一致。
- 目标局部区域已按要求替换、遮盖或清理。
- 未选中区域视觉上保持不变。
- 文件名保持不变；如果使用输出目录，只改变目录不改变文件名。
- 覆盖区域边缘没有明显突兀色块、残留像素或误遮挡。
