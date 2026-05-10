# hugo-skills

个人 Claude Code 技能集合。每个技能是 `skills/` 下的独立目录。

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
- 代码（变量名、函数名、注释、commit message）使用英文；文档（`SKILL.md`、`README.md`、`CLAUDE.md` 等 `.md` 文件）以简体中文为主。

## 添加新技能

1. 创建 `skills/<name>/SKILL.md`——记录触发短语、快速开始和选项。
2. 脚本放入 `skills/<name>/scripts/`，依赖写入 `skills/<name>/resources/requirements.txt`。
3. 在 `README.md` 的表格中添加一行。

## 可用技能

- **learning-master** — 六阶段学习助手，用于系统化学习课程、书籍和文章。
- **markdown-conversion** — 将 PDF / Word / Excel / PowerPoint / EPUB / HTML / 字幕 / URL 转换为 Markdown。
