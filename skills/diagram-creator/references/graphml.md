# GraphML

创建或编辑 `.graphml` 文件时读取本参考。GraphML 是基于 XML 的图数据交换格式，适合工具互操作和保存节点、边及属性；它不是人工精排流程图的默认格式。

## 文件骨架

```xml
<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">
  <key id="label" for="node" attr.name="label" attr.type="string"/>
  <key id="relation" for="edge" attr.name="relation" attr.type="string"/>
  <graph id="G" edgedefault="directed">
    <node id="client"><data key="label">客户端</data></node>
    <node id="api"><data key="label">API 服务</data></node>
    <edge id="e1" source="client" target="api"><data key="relation">HTTPS</data></edge>
  </graph>
</graphml>
```

## 建模要求

- 根元素使用 GraphML 命名空间；每个 `graph` 明确 `edgedefault="directed"` 或 `undirected`。
- 节点 ID 在文档内唯一，边的 `source` 和 `target` 引用已有节点。
- 自定义数据先用 `<key>` 声明，再用 `<data key="...">` 写入；属性类型与声明一致。
- 需要嵌套图、端口或超边时遵循 GraphML 原生结构，不用字符串字段模拟。

## 布局和兼容

GraphML 核心描述图结构，不统一规定视觉布局。yEd、Gephi 等工具可能使用各自扩展保存几何和样式：

- 以数据交换为目标时优先标准 GraphML 核心，减少厂商扩展。
- 以特定编辑器往返为目标时保留该编辑器已有命名空间和扩展数据，不做无意义重写。
- 不承诺一种工具的私有布局在另一工具中完全一致。

## 安全与验证

所有文本按 XML 规则转义。默认不使用外部实体、远程 schema 下载或不受信任的扩展内容。离线校验器检查根元素、ID、key 与边引用；交付前再用目标图编辑器打开验证兼容性。
