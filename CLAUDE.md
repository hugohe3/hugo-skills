# hugo-skills

This repo is a public collection of Claude Code skills. Each skill is a self-contained directory under `skills/`.

## Layout

```
skills/<skill-name>/
  SKILL.md          # Skill manifest (frontmatter + usage docs)
  scripts/          # Executable scripts the skill calls
  resources/        # Config, requirements, static assets
```

## Conventions

- Every skill must have a `SKILL.md` with YAML frontmatter (`name`, `description`).
- Scripts should be runnable standalone as CLIs, not only via the skill dispatcher.
- Python dependencies go in `resources/requirements.txt`. Pin major versions.
- No secrets committed — use env vars or a gitignored config file.

## Adding a new skill

1. Create `skills/<name>/SKILL.md` — document the trigger phrases, quick start, and options.
2. Put scripts in `skills/<name>/scripts/` and deps in `skills/<name>/resources/requirements.txt`.
3. Add a row to the table in `README.md`.

## Available skills

- **markdown-conversion** — converts PDF / Word / Excel / PowerPoint / EPUB / HTML / subtitles / URLs to Markdown.
