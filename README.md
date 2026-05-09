# hugo-skills

A collection of Claude Code skills for everyday workflows.

## What are skills?

[Claude Code skills](https://docs.anthropic.com/en/docs/claude-code/skills) are reusable, self-contained tools you can drop into any Claude Code project. Each skill lives in its own directory under `skills/` and comes with a `SKILL.md` that tells Claude how to invoke it.

## Skills

| Skill | Description |
|---|---|
| [markdown-conversion](skills/markdown-conversion/SKILL.md) | Convert PDF / Word / Excel / PowerPoint / EPUB / HTML / subtitles / web URLs into clean Markdown, ready for LLMs to read |

## Usage

Reference a skill from any Claude Code project by adding it to `.claude/settings.json`:

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

Or install via the Claude Code CLI:

```bash
claude skills add /path/to/hugo-skills/skills/markdown-conversion/SKILL.md
```

Once added, Claude will automatically invoke the skill when you ask to convert a document.

## Repository structure

```
skills/
  markdown-conversion/
    SKILL.md              # Skill manifest — Claude reads this
    scripts/              # Python converters (one per format)
    resources/            # requirements.txt, config.example.json
```

## Contributing

Bug reports and pull requests are welcome.
