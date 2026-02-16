# AGENTS.md

Repository guidance for AI coding agents and contributors.

## Purpose

This repo hosts reusable skills that are installed via `npx skills@latest add`.
Changes should preserve compatibility with the `vercel-labs/skills` package format.

## Required Skill Structure

Each skill must live at:

`skills/<skill-name>/SKILL.md`

Recommended structure:

```text
skills/<skill-name>/
  SKILL.md
  agents/openai.yaml
  scripts/
  references/
  assets/
```

## Authoring Rules

- Keep `SKILL.md` frontmatter valid:
  - `name`: lowercase letters/digits/hyphens only, <= 64 chars
  - `description`: concise trigger guidance
- Keep `<skill-name>` aligned with frontmatter `name`.
- Use relative paths inside `SKILL.md` (relative to the skill directory).
- Keep `SKILL.md` concise; move detailed material into `references/` when needed.
- Avoid committing secrets in any skill assets, scripts, or examples.
- Keep `agents/openai.yaml` aligned with the behavior described in `SKILL.md`.

## Repo-Specific Notes

- Current published skill: `skills/oracle`.
- If you add more skills, keep one folder per skill under `skills/`.
- Update `README.md` install examples when skill names change.
