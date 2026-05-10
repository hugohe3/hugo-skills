# hugo-skills

个人 Claude Code 技能集合，用于日常工作流。

## 什么是技能？

[Claude Code 技能](https://docs.anthropic.com/en/docs/claude-code/skills) 是可复用的独立工具，可以添加到任意 Claude Code 项目中。每个技能位于 `skills/` 下的独立目录，附带一个 `SKILL.md` 告诉 Claude 如何调用它。

## 技能列表

| 技能 | 说明 |
|---|---|
| [markdown-conversion](skills/markdown-conversion/SKILL.md) | 将 PDF / Word / Excel / PowerPoint / EPUB / HTML / 字幕 / 网页 URL 转换为干净的 Markdown，供 LLM 读取 |

## 使用方法

在任意 Claude Code 项目的 `.claude/settings.json` 中引用技能：

```json
{
  "skills": [
    {
      "type": "file",
      "path": "/path/to/hugo-skills/skills/markdown-conversion/SKILL.md"
    }
  ]
}
```

或通过 Claude Code CLI 安装：

```bash
claude skills add /path/to/hugo-skills/skills/markdown-conversion/SKILL.md
```

添加后，Claude 会在你要求转换文档时自动调用该技能。

## 仓库结构

```
skills/
  markdown-conversion/
    SKILL.md              # 技能清单——Claude 读取此文件
    scripts/              # Python 转换器（每种格式一个）
    resources/            # requirements.txt、config.example.json
```

## 贡献

欢迎提交 Bug 报告和 Pull Request。
