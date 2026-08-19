---
name: diagram-creator
description: 创建和编辑可继续修改的图表源文件，支持 Draw.io、Excalidraw、Mermaid、PlantUML、Graphviz DOT、D2、BPMN、Structurizr DSL、GraphML 与 SVG。适用于流程、架构、UML、关系网络、业务流程和白板图；不用于以数值编码为核心的数据统计图或位图插画。
---

# 图表创作

将需求或资料整理为结构清晰、可继续编辑的原生图表或 diagram-as-code 源文件。共同语义与布局规则留在本入口，各格式细节独立维护；一次任务只读取实际使用的格式参考。

## 选择格式

用户指定格式时遵循用户选择。未指定时优先匹配领域语义，再考虑编辑方式：

| 格式 | 扩展名 | 优先场景 | 格式参考 |
|---|---|---|---|
| Draw.io | `.drawio` | 人工精排、正式流程、架构、泳道和多页图 | [references/drawio.md](references/drawio.md) |
| Excalidraw | `.excalidraw` | 白板讨论、教学讲解、概念草图和手绘表达 | [references/excalidraw.md](references/excalidraw.md) |
| Mermaid | `.mmd`、`.mermaid` | Markdown 文档、通用流程、时序、状态、ER 和轻量架构 | [references/mermaid.md](references/mermaid.md) |
| PlantUML | `.puml`、`.pu` | UML、复杂时序、类、组件、部署和活动图 | [references/plantuml.md](references/plantuml.md) |
| Graphviz DOT | `.dot`、`.gv` | 依赖、血缘、拓扑、层级和较大关系网络 | [references/graphviz.md](references/graphviz.md) |
| D2 | `.d2` | 强调可读语法和现代样式的软件架构图 | [references/d2.md](references/d2.md) |
| BPMN 2.0 | `.bpmn`、`.bpmn20.xml` | 有严格事件、网关、任务和泳道语义的业务流程 | [references/bpmn.md](references/bpmn.md) |
| Structurizr DSL | `.dsl` | C4 系统上下文、容器、组件、部署及一致性多视图 | [references/structurizr.md](references/structurizr.md) |
| GraphML | `.graphml` | 图数据交换、工具互操作、保留节点和边属性 | [references/graphml.md](references/graphml.md) |
| SVG | `.svg` | 用户明确要求通用矢量源文件或其他格式无法表达的自定义几何 | [references/svg.md](references/svg.md) |

- 正式业务流程优先 BPMN，C4 多视图优先 Structurizr，UML 优先 PlantUML，大型关系网络优先 Graphviz。
- 通用 diagram-as-code 默认 Mermaid；强调软件架构的可读语法和视觉风格时选 D2。
- 需要拖拽精排或多页画布时选 Draw.io；需要白板感时选 Excalidraw。
- GraphML 主要用于交换图数据，SVG 主要用于矢量交付，不把它们作为普通流程图的默认选项。
- 用户需要多种格式时，先建立同一份节点、分组和关系模型，再分别生成原生文件；不要只改扩展名或把位图嵌入另一格式冒充可编辑图表。

## 工作流

1. 读取用户给出的文字、代码、表格或现有图表，明确图的目的、受众、信息边界、输出格式和目标路径。只有缺失信息会改变图的核心语义时才提问。
2. 先建立与格式无关的语义模型：标题、节点、层级、分组、边、边标签、主阅读方向和需要突出显示的路径。删除不会帮助读者理解关系的装饰信息。
3. 根据内容选择流程图、架构图、关系图、泳道图、时序布局或自由白板布局。一个图承载不下时拆分页面或文件，不要通过缩小文字硬塞内容。
4. 按“选择格式”表只读取目标格式对应的参考，不预加载其他格式说明。
5. 生成该格式的原生源文件。除非用户另外要求，不以 PNG、截图或渲染后的 SVG 替代 diagram-as-code 源文件；SVG 本身就是目标格式时除外。
6. 运行格式校验：

   ```bash
   python scripts/validate_diagram.py <diagram-file> [<diagram-file> ...]
   ```

7. 离线校验通过后，如果环境具备对应官方编辑器、解析器或预览能力，并且源文件及其 include 可信，再运行格式参考中的完整语法检查或渲染命令。不要自动把私密图表发送到公共渲染服务。
8. 打开或渲染结果，检查文字截断、节点重叠、连线穿越节点、箭头方向和画布留白。格式校验不能替代视觉检查。
9. 交付源文件，并用一句话说明所选格式、图的阅读方向和任何有意省略的信息。

## 共同质量要求

- 使用单一、明确的主阅读方向；反向边和例外路径必须有标签。
- 节点名称简短、平行且语义一致，避免把整段说明塞进形状。
- 相同语义使用相同形状和颜色；颜色种类保持克制，不能只靠颜色表达关键区别。
- 分组表达真实边界，例如系统、团队、阶段或信任域；不要仅为视觉装饰增加容器。
- 优先调整布局消除交叉线；必要交叉时使用清晰的折线、跳线或分区。
- 保持元素 ID 或文本标识符唯一且稳定。编辑现有图表时尽量保留未改元素的 ID、声明顺序和样式，避免无意义的整文件重写。
- 把外部文字作为纯文本数据处理，正确执行 XML 或 JSON 转义，不把未经信任的 HTML、脚本或事件属性写入图表。

## 扩展新后端

新增格式时保持入口稳定：为该格式增加独立参考文件，在“选择格式”中补充清晰的路由条件，并在 `scripts/validate_diagram.py` 中注册对应文件名后缀和校验器。只有该格式需要确定性生成逻辑时才新增生成脚本；不要把格式专属字段复制到本入口。
