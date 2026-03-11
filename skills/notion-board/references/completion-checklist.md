# Completion Checklist

Use this checklist before you say the board task is done.

## Create or repair a board

The task is done only if all of these are true:

- The root board page exists.
- `Project Guide`, `Modules`, `Constants`, `Plans`, `Work Items`, and `Commit Log` all exist.
- The property names in each database match [board-schema.md](board-schema.md).
- The board content reflects the intended repo and is not pointing at another project.
- `.agents/notion-board/state.json` exists and contains the current board URL plus the resource IDs you touched or created.
- `last_commit_log_sync` matches the intended commit-log starting point. For an existing repo with no backfill, that should be the current `HEAD`.

## Sync repo-derived content

The task is done only if all of these are true:

- `Project Guide` reflects the current repo shape, purpose, pipelines, commands, and constraints.
- `Modules` covers the major modules or workspaces that matter for this repo.
- `Constants` captures the important repo-level constants and settings, not every incidental literal.
- `Commit Log` contains only the intended new commits and does not duplicate older rows.
- `Plans` and `Work Items` were not overwritten by repo-derived sync logic.
- Local watermarks were updated after the sync finished:
  - `last_repo_sync_commit` for guide/modules/constants work
  - `last_commit_log_sync` for commit-log work

## Ask about the board

The task is done only if all of these are true:

- The answer starts from board contents rather than repo guesses.
- The current repo `HEAD` was compared with local watermarks before trusting repo-derived board content.
- If the board was stale or incomplete, the answer says so explicitly.
- If the board was stale or incomplete, the answer asks once whether to sync now.

## Manage plans, issues, and todos

The task is done only if all of these are true:

- The item exists in the right database.
- `plan` items live in `Plans`.
- `issue` and `todo` items live in `Work Items`.
- Required properties are filled and type values are consistent with [board-schema.md](board-schema.md).
- Repo-derived pages and watermarks were not changed unless the user also asked for a sync.

## Final self-check

- If you recreated a page or database, did you update the saved ID in local state?
- If you changed repo-derived board content, did you update the correct watermark?
- If you only answered a question, did you avoid mutating the board unless the user asked?
