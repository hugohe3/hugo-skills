# Mermaid

创建或编辑 `.mmd`、`.mermaid` 源文件时读取本参考。Mermaid 适合嵌入 Markdown 和版本控制的轻量 diagram-as-code；源文件只保存 Mermaid 定义，不包含 Markdown 代码围栏。

## 选择图类型

- 通用流程和轻量架构：`flowchart`
- 交互过程：`sequenceDiagram`
- 静态结构：`classDiagram`
- 生命周期：`stateDiagram-v2`
- 数据关系：`erDiagram`
- 计划和阶段：`gantt`、`timeline`
- 概念发散：`mindmap`

不要因为 Mermaid 支持某种语法就强行使用它；正式 BPMN、完整 C4 模型或大型关系网络应使用对应专用后端。

## 基本结构

```mermaid
flowchart LR
    client[客户端] -->|HTTPS| api[API 服务]
    api -->|查询| db[(数据库)]
```

- 第一条有效语句声明图类型和方向。
- 节点使用简短、稳定的 ASCII 标识符，显示文字放在标签中。
- 含空格、标点或特殊字符的标签使用引号或相应形状语法，避免让显示文字兼任标识符。
- 先依靠自动布局；只有必要时再增加子图、不可见关系或布局配置。
- 使用 `subgraph` 表达真实系统或职责边界，并为每个子图提供有意义的名称。

## 可读性与安全

- 一个文件默认只放一张图；多张图拆分文件，便于渲染器和文档工具处理。
- 样式集中使用 `classDef` 与 `class`，不要在每个节点重复长样式。
- 避免未经信任的 HTML 标签、`click` 链接和初始化脚本。外部文字按 Mermaid 标签规则转义。
- Mermaid 版本间可能增加新图类型；修改现有文件时遵循项目当前渲染器版本，不主动升级语法。

## 完整验证

离线校验脚本只检查文件边界和图类型入口。安装官方 Mermaid CLI 后，可对可信源文件渲染验证：

```bash
mmdc -i input.mmd -o preview.svg
```

最终检查自动布局是否造成标签截断、子图重叠或边标签歧义。
