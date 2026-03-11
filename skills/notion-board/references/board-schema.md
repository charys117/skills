# Board Schema

Use this schema no matter which Notion surface you choose.

## Root structure

- Root page title: `<repo-name> Board` unless the user names a different title.
- Child page: `Project Guide`
- Child databases: `Modules`, `Constants`, `Plans`, `Work Items`, `Commit Log`

## Project Guide

Rewrite this page on repo sync. Keep the body organized into these sections:

- `Project Metadata`: repo name, branch, current `HEAD`
- `Architecture`: repo purpose, stack signals, module roots
- `Pipelines`: CI, deploy, build, and test signals inferred from the repo
- `External Dependencies`: runtime or platform signals inferred from tracked files
- `Key Commands`: top-level commands worth keeping visible
- `Important Constraints`: setup or workflow constraints that affect contributors

## Databases

### Modules

Use one row per major module or workspace.

- Title property: `Name`
- Other properties: `Path`, `Type`, `Depends On`, `Last Synced`
- Upsert key: `Path`
- Page body: summary, module details, dependencies, pipeline, notes

### Constants

Use one row per important repo-level constant or setting.

- Title property: `Name`
- Other properties: `Kind`, `Path`, `Default/Value`, `Impact`
- Upsert key: `Name + Path`
- Page body: impact summary plus the captured value and source path

### Plans

Use this database for notion-only plans.

- Title property: `Name`
- Other properties: `Status`, `Target Date`, `Summary`
- Upsert key: `Name`
- Page body: summary and notes

### Work Items

Use this database for notion-only issues and todos.

- Title property: `Name`
- Other properties: `Type`, `Status`, `Priority`, `Plan`, `Module/Area`, `Source`, `Notes`
- `Type` values: `Issue`, `Todo`
- Upsert key: `Name + Type`
- Page body: summary and notes

### Commit Log

Use this database only for commits that happen after the board binding is created.

- Title property: `Commit`
- Other properties: `Summary`, `Author`, `Date`, `Area`
- Upsert key: 12-character short SHA stored in `Commit`
- Page body: full commit body plus changed files

## Watermarks and state

Persist these values in `.agents/notion-board/state.json`:

- `schema_version`
- `repo_root`
- `repo_name`
- `notion_profile`
- `board_page_id`
- `board_url`
- `project_guide_page_id`
- `modules_db_id`
- `constants_db_id`
- `plans_db_id`
- `work_items_db_id`
- `commit_log_db_id`
- `last_repo_sync_commit`
- `last_commit_log_sync`

Use the watermarks this way:

- Set `last_commit_log_sync` to the current `HEAD` during first init on an existing repo. Do not backfill older commits.
- Update `last_repo_sync_commit` after syncing `Project Guide`, `Modules`, or `Constants`.
- Update `last_commit_log_sync` after appending unsynced commits.
- Treat any mismatch between current `HEAD` and either watermark as a stale signal during `ask about board`.
