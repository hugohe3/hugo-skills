# SVG

创建或编辑 `.svg` 文件时读取本参考。SVG 是通用矢量源格式，适合需要精确几何、网页嵌入、跨工具查看或其他后端无法表达的自定义图；它不保留 UML、BPMN、C4 等高级语义。

## 文件骨架

```xml
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 450" role="img" aria-labelledby="title desc">
  <title id="title">系统架构</title>
  <desc id="desc">客户端通过 API 服务访问数据库。</desc>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="#4b5563"/>
    </marker>
  </defs>
  <g id="nodes" font-family="Arial, sans-serif">
    <rect x="80" y="170" width="160" height="70" rx="10" fill="#dae8fc" stroke="#6c8ebf"/>
    <text x="160" y="212" text-anchor="middle">客户端</text>
  </g>
</svg>
```

## 结构和布局

- 必须提供 `viewBox`，并让画布覆盖所有可见元素；`width`、`height` 可按交付场景选填。
- 用描述性 `<g id="...">` 分组节点、连线、标签和图例，保持元素 ID 唯一稳定。
- 复用箭头、渐变、滤镜等定义时放入 `<defs>`，通过引用使用。
- 文字默认保持为 `<text>` 以便编辑和无障碍访问；只有用户明确要求外观完全固定时才转路径。
- 为信息图提供 `<title>` 和 `<desc>`，不能只靠颜色表达关键区别。

## 安全边界

默认生成静态安全 SVG：

- 不使用 `<script>`、事件处理属性或可执行链接。
- 不使用 `<foreignObject>` 嵌入任意 HTML。
- 不引用远程图片、字体、样式或文档；必要的位图使用用户提供的可信资源并明确是否内嵌。
- 外部文字按 XML 规则转义，不能直接拼接为标签或属性。

## 验证

离线校验器检查 XML、SVG 根元素、`viewBox`、ID、引用和危险主动内容。交付前在目标浏览器或矢量编辑器中打开，检查字体回退、裁切、连线端点和缩放后的清晰度。
