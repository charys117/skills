---
name: notion-board
description: Use Notion as the primary interface for repository architecture, pipelines, modules, constants, plans, todos, issues, and commit logs. Use when Codex needs to create or update a repo-backed Notion board, answer questions from board contents, keep repo-derived content synced one-way from the repo into Notion, or save the board location locally without exposing that state in git.
---

# Notion Board

Use this skill to make Notion the working surface for a repository while keeping technical facts sourced from the repo.

## Operating model

- Treat Notion interaction as backend-agnostic. Use whatever Notion capability already exists in the current session.
- Do not add backend-specific workflow to this skill.
- Keep the Notion data model fixed regardless of the backend. Read [references/board-schema.md](references/board-schema.md) before creating or repairing the board.
- Use `scripts/notion_board.py` only for local state management after the Notion work is done.

## Create or bind a board

1. Resolve the repo root. Prefer `git rev-parse --show-toplevel`; if it fails, use the current directory and call out the downgrade.
2. Check `.agents/notion-board/state.json` for an existing local binding.
3. If the board already exists, inspect it and confirm whether it already matches the schema in [references/board-schema.md](references/board-schema.md).
4. If the board does not exist, create the root page, `Project Guide`, and the required databases.
5. After the board exists, write the local binding with:

```bash
python3 scripts/notion_board.py bind \
  --board-url "<board-url>" \
  --project-guide-page-id "<page-id>" \
  --modules-db-id "<db-id>" \
  --constants-db-id "<db-id>" \
  --plans-db-id "<db-id>" \
  --work-items-db-id "<db-id>" \
  --commit-log-db-id "<db-id>"
```

Use `--last-commit-log-sync HEAD` on first bind for an existing repo unless you explicitly backfilled commit history.

## Update the board

- Sync only repo-derived technical content from repo to Notion.
- Keep `Plans` and `Work Items` as Notion-only project-management data.
- Update `Project Guide`, `Modules`, `Constants`, and `Commit Log` without overwriting manually maintained project-management content.
- After a successful repo-derived sync, update local watermarks with:

```bash
python3 scripts/notion_board.py mark-sync --repo-derived
python3 scripts/notion_board.py mark-sync --commit-log
python3 scripts/notion_board.py mark-sync --repo-derived --commit-log
```

## Ask about the board

- Answer from the board first.
- Read local state and compare current `HEAD` with the stored watermarks before trusting repo-derived board content.
- If the board is stale or missing relevant detail, inspect the repo, answer with that caveat, and ask once whether to sync the board now.
- Do not silently repair the board unless the user asks for it.

## Manage plans, issues, and todos

- Keep plans in `Plans`.
- Keep issues and todos in `Work Items`, with `Type=Issue` or `Type=Todo`.
- Do not sync these notion-only project-management records back into the repo.

## Decide whether the task is done

- Read [references/completion-checklist.md](references/completion-checklist.md) before closing the task.
- Do not call the task complete just because the Notion API call succeeded.
- A task is done only when the Notion structure/content is correct and the local binding or sync watermarks reflect the new reality.

## Local state

- Store binding state only in `.agents/notion-board/state.json`.
- Keep one default board per repo in v1.
- Warn if `.gitignore` does not ignore `.agents/`.
- Use `python3 scripts/notion_board.py status` to inspect the saved binding and staleness flags.
