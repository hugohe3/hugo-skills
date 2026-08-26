# hugo-skills

个人 AI 技能集合。每个技能是 `skills/` 下的独立目录，可迁移到支持 skill / agent skill 机制的平台使用。

## 目录结构

```
skills/<skill-name>/
  SKILL.md          # 技能清单（frontmatter + 使用文档）
  scripts/          # 技能调用的可执行脚本
  resources/        # 配置、依赖、静态资源
```

## 规范

- 每个技能必须有带 YAML frontmatter（`name`、`description`）的 `SKILL.md`。
- 脚本应可作为独立 CLI 运行，不仅限于通过技能调度器调用。
- Python 依赖写入 `resources/requirements.txt`，锁定主版本号。
- 不提交密钥——使用环境变量或 gitignore 的配置文件。
- 保持技能平台无关：`SKILL.md` frontmatter 只使用通用字段，避免写入特定平台专属配置。
- 代码（变量名、函数名、注释）使用英文；文档（`SKILL.md`、`README.md`、`CLAUDE.md` 等 `.md` 文件）以简体中文为主。
- Markdown 格式规范：在中文文档中对词汇进行加粗时，应避免星号 `**` 直接贴合中文全角标点（如 `“`、`”`、`《`、`》` 等），否则在部分解析器中会导致加粗渲染失效。最佳实践是“标点外置”，例如使用 `“**词汇**”` 而非 `**“词汇”**`，或者在加粗块的前后保留空格。
- Commit message 使用 Conventional Commits 风格，格式为 `type(scope): 中文描述` 或 `type: 中文描述`；`type` / `scope` 保持英文，描述使用简体中文。示例：`feat(learning-master): 添加六阶段学习工作流技能`、`docs: 完善通用技能安装和使用说明`。

## 产物位置

生成或修改文件时按以下优先级确定最终位置：

1. 用户明确指定输出路径时，使用该路径。
2. 基于已有本地源文件进行编辑、转换或派生时，默认输出到源文件所在目录；需要保留原文件时使用不冲突的新文件名。
3. 当前任务已经属于某个现有项目时，沿用该项目目录，不创建重复项目。
4. 没有本地源文件的新产物，默认保存到 `projects/<YYYYMMDD>-<简短主题>/`。

技能或任务明确规定了专用项目目录时，按其规定执行。系统临时目录、Codex 可视化目录和工具缓存只能存放中间文件，不得作为最终交付位置。

## 添加新技能

1. 创建 `skills/<name>/SKILL.md`——记录触发短语、快速开始和选项。
2. 脚本放入 `skills/<name>/scripts/`，依赖写入 `skills/<name>/resources/requirements.txt`。
3. 在 `README.md` 的表格中添加一行。

## 可用技能

- **bilibili-subtitles** — 批量获取 Bilibili 视频或指定 UP 主的公开字幕轨道，导出为 SRT 并保存到 PPT Master 的 projects 目录。
- **diagram-creator** — 创建和编辑可继续修改的多格式图表源文件，支持 Draw.io、Excalidraw、Mermaid、PlantUML、Graphviz、D2、BPMN、Structurizr、GraphML 与 SVG。
- **geospatial-converter** — 统一处理坐标换算、XLSX/CSV 生成 Shapefile、SHP 导出 DXF/DWG、ODA 回转验证、截图叠加 KML 面，以及地方独立坐标系的安全识别。
- **learning-master** — 六阶段学习助手，用于系统化学习课程、书籍和文章。
- **markdown-conversion** — 将 PDF / Word / Excel / PowerPoint / EPUB / HTML / 字幕 / URL 转换为 Markdown。
- **pdf-transcription** — 使用模型视觉理解将普通或影印 PDF 高保真转录为经过校核、可直接收录的结构化 Markdown。
- **structured-problem-solving** — 用麦肯锡七步问题解决法分析复杂问题，结合逐问澄清、术语统一、决策地图、MECE 拆解、优先排序、分析论证和方案呈现形成解决路径。
- **wind-turbine-dwg-layout** — 将机位坐标 DWG 中的点位批量写入新底图，以风机示意图、25×25 方框和 `HD数字#` 编号组成标准 IB 风机布置。
- **wind-power-business** — 风电业务技能框架，当前支持根据功率曲线调用脚本计算 Cp 值、逐风速明细和最大功率系数。
