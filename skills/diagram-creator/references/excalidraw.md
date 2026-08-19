# Excalidraw 原生格式

需要创建或编辑 `.excalidraw` 文件时读取本参考。该文件是 UTF-8 JSON 场景，不是 SVG 或截图。

## 文件骨架

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [],
  "appState": {
    "gridSize": null,
    "viewBackgroundColor": "#ffffff"
  },
  "files": {}
}
```

- `elements` 按绘制顺序存放形状、文本、箭头和分组元素。
- `appState` 只保留需要随文件交付的画布设置，不要复制编辑器的临时选择和协作状态。
- 没有图片时仍可保留空的 `files` 对象；图片元素必须通过 `fileId` 引用其中真实存在的数据。

## 元素共同字段

创建元素时使用稳定且唯一的字符串 ID，并提供 Excalidraw 恢复场景所需的常见字段：

```json
{
  "id": "api",
  "type": "rectangle",
  "x": 120,
  "y": 100,
  "width": 180,
  "height": 70,
  "angle": 0,
  "strokeColor": "#1e1e1e",
  "backgroundColor": "#a5d8ff",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "groupIds": [],
  "frameId": null,
  "roundness": {"type": 3},
  "seed": 101,
  "version": 1,
  "versionNonce": 1001,
  "isDeleted": false,
  "boundElements": null,
  "updated": 1,
  "link": null,
  "locked": false
}
```

- 常用形状类型为 `rectangle`、`diamond`、`ellipse`、`text`、`arrow`、`line`、`freedraw` 和 `frame`。
- `seed` 与 `versionNonce` 使用稳定整数；不要对现有元素无意义地重置这些值。
- 手绘感来自 `roughness`，而不是故意制造不对齐或文字重叠。

## 文本与绑定

文本元素至少还要提供 `text`、`originalText`、`fontSize`、`fontFamily`、`textAlign`、`verticalAlign`、`lineHeight`、`containerId` 和 `autoResize`。节点内文字可作为独立文本精确放置；需要随容器移动时：

- 文本的 `containerId` 指向形状 ID。
- 形状的 `boundElements` 包含 `{"type": "text", "id": "..."}`。
- 文本坐标和宽高仍需显式设置，不能假设 `containerId` 会自动完成排版。

中文标签优先使用编辑器当前支持中日韩字符的字体，并在视觉检查时确认字体回退没有造成截断。标签较长时增加节点宽度或主动换行，不要单纯缩小字号。

## 箭头与线

箭头和线使用相对于元素起点的 `points`，例如 `[[0, 0], [180, 0]]`。箭头通常还包含：

- `startArrowhead: null` 与 `endArrowhead: "arrow"`
- `startBinding`、`endBinding`，其中 `elementId` 引用已有节点
- `lastCommittedPoint: null`

使用绑定时，把箭头 ID 同步加入两端节点的 `boundElements`。若箭头不绑定节点，则端点坐标必须留出清晰间距，避免箭头压在形状或文字上。

## 布局

- 保留自然但受控的手绘感；同类节点仍应有一致尺寸和大致对齐。
- 节点之间至少留 80–120 像素，给箭头、手写标签和讨论批注留下空间。
- 颜色使用低饱和背景与深色描边；重点节点只使用一种强调色。
- 自由批注与主流程分区放置，不让批注线穿过关键关系。

## 校验重点

- JSON 可解析，顶层 `type` 为 `excalidraw`，`version` 为正整数。
- `elements` 是数组，元素 ID 唯一，几何字段为有限数字。
- 文本字段类型正确；箭头和线至少有两个合法点。
- `containerId`、`frameId`、绑定关系和图片 `fileId` 引用存在。
- 打开场景后检查中文字体、绑定位置、箭头端点和元素层叠顺序。
