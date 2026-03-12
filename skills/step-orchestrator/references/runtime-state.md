# Runtime State

Use local runtime-state files to judge subagent liveness during long-running rounds.

## Layout

- Runtime-state root: `<repo_root>/.agents/step-orchestrator/rounds/`
- Step directory: `<repo_root>/.agents/step-orchestrator/rounds/step-<step-id>/`
- Round file pattern:
  - `A1.json`, `A2.json`, ... for implementer rounds
  - `B1.json`, `B2.json`, ... for reviewer rounds
- Example path: `<repo_root>/.agents/step-orchestrator/rounds/step-3/A1.json`

Keep these files local-only. Do not commit them and do not copy heartbeat entries into the step table.

## Helper script

Resolve [scripts/step_orchestrator_state.py](../scripts/step_orchestrator_state.py) from this skill directory and invoke that resolved path explicitly. Do not assume the target repo has the helper under its own `scripts/` directory.
Treat `--repo-root` as the exact workspace root for state files. Do not auto-promote it to the enclosing git toplevel in nested workspace or monorepo setups.

Commands:

- `start`: create the round file at the coordinator-assigned path and claim ownership of the round; require `step_id`, `step_title`, `role`, and `round`
- `heartbeat`: refresh timestamps, phase, checkpoint, and next step
- `read`: load the state plus freshness and replacement guidance
- `finish`: close the round with `done` or `superseded`
- `block`: close the round with a blocker reason

## JSON shape

Minimal fields:

- `step_id`
- `step_title`
- `role`
- `round`
- `owner`
- `status`
- `started_at`
- `last_heartbeat_at`
- `phase`
- `last_checkpoint`
- `next_step`
- `next_update_due_at`
- `summary`
- `blocker`

Status values:

- `starting`
- `running`
- `done`
- `blocked`
- `superseded`

## Freshness rules

- The coordinator assigns the round-state file path but does not pre-create the file.
- Write `start` as the first concrete action in the round.
- Write `heartbeat` on every milestone or at least every 5 minutes.
- `read` interprets the round as:
  - `fresh` when the file is still inside its current heartbeat window
  - `stale_once` after one missed heartbeat window; nudge the current subagent
  - `stale_twice` after two missed heartbeat windows; replace the subagent
- Hitting the heartbeat boundary counts as missed. There is no extra grace interval at exactly one or two full windows.
- Terminal states (`done`, `blocked`, `superseded`) are not stale.

## Authority and replacement

- The authoritative round for a step and role is the highest round number that still matters for that role.
- A replacement never reuses the previous file. `A2.json` replaces `A1.json`; `B2.json` replaces `B1.json`.
- When replacing a round:
  1. Read the authoritative file.
  2. Capture `last_checkpoint`, `next_step`, and `summary`.
  3. Mark the prior round `superseded`.
  4. Spawn the next round with the carried-forward checkpoint context.
- The helper rejects new `heartbeat`, `finish`, or `block` writes to a superseded round. This prevents late writes from an older round from overriding the current one.
- A superseded round is frozen. Re-running `finish --status superseded` against it must fail instead of mutating timestamps or summaries.
