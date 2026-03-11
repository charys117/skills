# Skills Repository

This repository contains installable skills in the format used by
[`vercel-labs/skills`](https://github.com/vercel-labs/skills).

## Install

Replace `<owner>/<repo>` with this repository path on GitHub.

```bash
# List skills in this package
npx skills@latest add <owner>/<repo> --list

# Install one skill
npx skills@latest add <owner>/<repo> --skill notion-board
npx skills@latest add <owner>/<repo> --skill oracle
npx skills@latest add <owner>/<repo> --skill step-orchestrator

# Install all skills in this package
npx skills@latest add <owner>/<repo>
```

Current skills in this repo: `notion-board`, `oracle`, `step-orchestrator`.

## Repository Layout

```text
skills/
  notion-board/
    SKILL.md
    agents/openai.yaml
    scripts/
    references/
  oracle/
    SKILL.md
    agents/openai.yaml
    scripts/
    assets/
  step-orchestrator/
    SKILL.md
    agents/openai.yaml
    references/
```

## Skill Package Requirements

This repo follows the public package format documented by Agent Skills:

- Skill discovery path: `skills/<skill-name>/SKILL.md`
- `SKILL.md` must start with YAML frontmatter containing:
  - `name` (lowercase letters, digits, hyphens; should match `<skill-name>`)
  - `description` (clear trigger guidance)
- Paths referenced in `SKILL.md` should be relative to the skill directory.
- `agents/openai.yaml` is recommended for UI metadata.

References:

- https://github.com/vercel-labs/skills
- https://skills-spec.agentskills.io/skill-format
