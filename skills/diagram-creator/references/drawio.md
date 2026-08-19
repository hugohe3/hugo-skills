# Draw.io 原生格式

需要创建或编辑 `.drawio` 文件时读取本参考。默认生成未压缩 XML：Draw.io 原生支持该形式，文本差异可审查，也便于后续 agent 修改。

## 文件骨架

```xml
<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" compressed="false">
  <diagram id="page-main" name="Page-1">
    <mxGraphModel grid="1" gridSize="10" guides="1" connect="1" arrows="1" page="1" pageScale="1" pageWidth="1169" pageHeight="827" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <!-- vertices and edges -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

- 每个 `<diagram>` 代表一个页面，并拥有唯一 `id`。
- `id="0"` 是根，`id="1" parent="0"` 是默认图层；普通元素默认使用 `parent="1"`。
- 不要手工压缩新文件。编辑已有压缩文件时，可先用 Draw.io 导出为未压缩 XML，再进行结构化修改。

## 节点和连线

普通节点：

```xml
<mxCell id="api" value="API 服务" style="rounded=1;whiteSpace=wrap;html=0;fillColor=#dae8fc;strokeColor=#6c8ebf;" vertex="1" parent="1">
  <mxGeometry x="120" y="100" width="160" height="60" as="geometry"/>
</mxCell>
```

普通连线：

```xml
<mxCell id="edge-api-db" value="查询" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=0;endArrow=block;endFill=1;" edge="1" parent="1" source="api" target="db">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

- 节点使用 `vertex="1"`，并提供非负宽高的 `<mxGeometry>`。
- 连线使用 `edge="1"`，`source` 与 `target` 引用已有节点 ID；常规连接的 geometry 使用 `relative="1"`。
- 坐标原点位于左上角，x 向右、y 向下。容器内子节点的坐标相对于容器。

## 常用形状

- 普通步骤：`rounded=1`
- 判断：`rhombus`
- 开始/结束：`ellipse`
- 数据库：`shape=cylinder3;boundedLbl=1;backgroundOutline=1`
- 分组或泳道：`swimlane;startSize=28`

所有形状都应补充 `whiteSpace=wrap;html=0` 及明确的 `fillColor`、`strokeColor`。默认使用纯文本标签；将 `&`、`<`、`>`、双引号等字符按 XML 属性规则转义。不要把外部输入拼接为 `html=1` 的标签。

## 布局

- 常规节点宽度以 140–200、高度以 50–80 为起点；同层节点保持一致尺寸。
- 相邻节点至少留出一个节点高度或约 60–100 像素，让标签与折线有空间。
- 流程默认从左到右或从上到下。架构图先确定分层或信任域，再布置域内组件。
- 先移动节点消除交叉线，再考虑手工加入 `mxPoint` 拐点。
- 多页图应让每页自洽，并使用描述性页面名称。

## 校验重点

- XML 可解析，根元素是 `<mxfile>`，每页包含一个 `<mxGraphModel>`。
- 每页具备结构单元 `0` 与 `1`，并且所有单元 ID 唯一。
- `parent`、`source`、`target` 引用存在。
- 节点有有效尺寸，连线 geometry 使用相对坐标。
- 标签经过 XML 转义，不含未经信任的 HTML 或脚本。
