# Graphviz DOT

创建或编辑 `.dot`、`.gv` 文件时读取本参考。Graphviz 适合依赖图、调用图、数据血缘、网络拓扑、层级结构和节点较多的关系网络。

## 文件骨架

```dot
digraph architecture {
  graph [rankdir=LR, bgcolor="transparent", nodesep=0.5, ranksep=0.8];
  node [shape=box, style="rounded,filled", fillcolor="#dae8fc", color="#6c8ebf", fontname="Arial"];
  edge [color="#5f6368", fontname="Arial", arrowsize=0.8];

  client [label="客户端"];
  api [label="API 服务"];
  db [label="数据库", shape=cylinder];

  client -> api [label="HTTPS"];
  api -> db [label="查询"];
}
```

- 有向关系使用 `digraph` 和 `->`，无向关系使用 `graph` 和 `--`。
- 节点标识符保持稳定；包含空格、标点或非 ASCII 字符的标识符和属性值使用双引号。
- `rankdir=LR` 适合流程和血缘，`rankdir=TB` 适合层级；不要用大量不可见边过度操纵布局。
- 使用 `subgraph cluster_*` 表达真实分组，集群名称和标签不能替代节点语义。

## 布局选择

- `dot`：有方向的层级或 DAG。
- `neato`、`fdp`：无向或弹簧布局。
- `sfdp`：更大的无向网络。
- `circo`、`twopi`：圆形或径向关系。

默认让图结构与布局引擎解耦；只有内容明确需要特定布局时才指定引擎。

## 标签与安全

优先使用普通字符串标签。HTML-like 标签必须满足 XML 转义规则，而且不应拼接未经信任的 HTML。外部图片、URL 和自定义字体只有在交付环境明确支持时才使用。

## 完整验证

安装 Graphviz 后，对有向图执行解析和渲染检查：

```bash
dot -Tsvg input.dot -o preview.svg
```

其他布局引擎使用对应命令。最终检查集群边界、重叠、过长边和标签是否可读。
