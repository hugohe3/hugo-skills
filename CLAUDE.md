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

## 添加新技能

1. 创建 `skills/<name>/SKILL.md`——记录触发短语、快速开始和选项。
2. 脚本放入 `skills/<name>/scripts/`，依赖写入 `skills/<name>/resources/requirements.txt`。
3. 在 `README.md` 的表格中添加一行。

## 可用技能

- **coordinate-converter** — 在 WGS84 / GCJ02（高德） / BD09（百度）坐标系之间批量换算经纬度，支持坐标列表与 CSV / TSV / GeoJSON / GPX / KML 文件原格式转换。
- **learning-master** — 六阶段学习助手，用于系统化学习课程、书籍和文章。
- **markdown-conversion** — 将 PDF / Word / Excel / PowerPoint / EPUB / HTML / 字幕 / URL 转换为 Markdown。
- **structured-problem-solving** — 用麦肯锡七步问题解决法分析复杂问题，结合逐问澄清、术语统一、决策地图、MECE 拆解、优先排序、分析论证和方案呈现形成解决路径。
- **wind-power-business** — 风电业务技能框架，当前支持根据功率曲线调用脚本计算 Cp 值、逐风速明细和最大功率系数。
