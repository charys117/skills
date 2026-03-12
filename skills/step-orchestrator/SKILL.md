---
name: step-orchestrator
description: >-
  Coordinate a multi-agent implementation and review loop from a step table, then
  commit each approved step and write the result back to the table. Use when Codex
  receives a natural-language request that names a step-table source or location,
  explicit step IDs or ranges such as 3-5,7, and a target workspace or repository,
  and the work should alternate implementer and reviewer agents until approval.
---

# Step Orchestrator

Coordinate one requested step at a time from a step table.

## Require these inputs

- Require a step-table source or location.
- Require explicit step IDs or ranges such as `3-5,7`.
- Require the target workspace or repository. Treat the current workspace as the default only when the user does not name another one.
- Accept tests, constraints, branch preferences, and acceptance criteria as optional additions.

## Load references only when needed

- Read [references/adapter-contract.md](references/adapter-contract.md) before mutating an unfamiliar backend.
- Read [references/runtime-state.md](references/runtime-state.md) before coordinating long-running rounds or replacing a stalled subagent.
- Choose the step-table interaction path from the context already available in the session, such as installed skills, MCP tools, repository utilities, or built-in capabilities.
- Stop and report a blocker if the current context cannot safely inspect and update the named step table.

## Run the coordinator loop

- Inspect the source schema before mutating anything.
- Resolve the requested range against a sortable numeric or order field.
- Normalize duplicates and process steps in ascending order.
- Handle one step at a time. Do not overlap steps.
- For each step:
  1. Mark the step `In Progress`.
  2. Allocate a round-state file path for `A1` under `<repo_root>/.agents/step-orchestrator/rounds/step-<id>/A1.json`. Do not pre-create the file.
  3. Spawn implementer `A1` to change code for only that step. Pass the allocated path with `--state-file`, instruct it to create that file with `start` as its first concrete action, keep it fresh on each milestone or within 5 minutes, and never commit, tag, or update the step table.
  4. Wait on the runtime-state file, not on chat silence. A fresh file means keep waiting even if the subagent has not sent an in-band message.
  5. Mark the step `In Review`.
  6. Allocate a round-state file path for `B1` and pass it the same way.
  7. Spawn reviewer `B1` to review only that step. Keep reviewer read-only and require the same runtime-state updates.
  8. Wait on the `B1` runtime-state file before doing any review work on the same step yourself.
  9. If reviewer `B1` rejects the work, append `B1` review history, set the step back to `In Progress`, and spawn implementer `A2` with the review notes plus the last recorded checkpoint and next step from the prior round-state file when they exist.
  10. Continue `A<n> -> B<n>` rounds until the reviewer approves or a hard blocker prevents safe progress.
  11. After approval, stage only the approved step's changes and commit `step {id}: {step_title}`.
  12. Mark the step `Done` and write back the approval summary plus commit SHA and message.
- Continue to the next requested step only after the current step is approved, committed, and written back.

## Keep side effects centralized

- Let implementer agents patch code and run the tests needed for that step.
- Let reviewer agents inspect and report findings, but never patch code.
- Let only the coordinator commit, update the step table, and decide whether a blocker is hard.
- While an implementer or reviewer round is active, let the coordinator orchestrate and wait. Do not let it silently absorb the same round just because the subagent is slow.

## Wait deliberately for spawned agents

- Treat each spawned `A<n>` or `B<n>` as the owner of that round until it finishes, reports a blocker, or is explicitly replaced.
- Resolve [scripts/step_orchestrator_state.py](scripts/step_orchestrator_state.py) from this skill directory and invoke that resolved path explicitly. Do not assume the target workspace has a matching `scripts/` path.
- Treat `--repo-root` as the exact workspace root chosen for this run, even when that workspace lives inside a larger git repository.
- Make the local runtime-state file the primary liveness signal for long-running rounds. Treat any native Codex CLI progress messages as supplemental only.
- Require the subagent to call `start` immediately, then `heartbeat` on every milestone or at least every 5 minutes.
- Use `read` against the authoritative round file to decide whether to wait, nudge, or replace:
  - `fresh` -> keep waiting
  - `stale_once` -> nudge the same subagent
  - `stale_twice` -> mark the prior round `superseded` and spawn the next round from the last checkpoint
- Do not treat a single timeout or lack of chat reply as proof that the subagent is stuck.
- Let the coordinator take over a round only when subagent execution is impossible in the current session, and record that reason in the review history or blocker notes.
- Never start the next step while any subagent still owns the current step.
- Never mirror heartbeat traffic into the step table. Keep runtime liveness local under `.agents/step-orchestrator/`.

## Use the runtime-state helper

Resolve [scripts/step_orchestrator_state.py](scripts/step_orchestrator_state.py) from this skill directory, then invoke that resolved file path. Example:

```bash
STATE_HELPER="<resolved path to this skill>/scripts/step_orchestrator_state.py"
STATE_FILE="$PWD/.agents/step-orchestrator/rounds/step-3/A1.json"

python3 "$STATE_HELPER" --repo-root "$PWD" start \
  --state-file "$STATE_FILE" \
  --step-id 3 \
  --step-title "wire login" \
  --role implementer \
  --round 1 \
  --owner A1

python3 "$STATE_HELPER" --repo-root "$PWD" heartbeat \
  --state-file "$STATE_FILE" \
  --phase "implementing auth flow" \
  --last-checkpoint "login endpoint compiles" \
  --next-step "add regression tests" \
  --summary "core path wired"

python3 "$STATE_HELPER" --repo-root "$PWD" read \
  --state-file "$STATE_FILE"
```

## Enforce the minimum contract

- Require one sortable numeric or order field for range resolution. Stop before mutation if it is missing.
- Infer a writable status field and map the local flow to `Todo`, `In Progress`, `In Review`, and `Done`. Stop before mutation if no writable status-like field exists.
- Infer notes and commit fields by name. If either field is missing, fall back to page-body or comment writeback instead of skipping the history.
- Append review history by round. Do not overwrite earlier `B1`, `B2`, or later reviewer feedback.
- Keep round-state files local-only. They track coordination liveness, not product state.
- Treat unsupported backends, missing required schema primitives, unrecoverable test or setup failures, or conflicting user changes as hard blockers. Write the blocker back when the backend allows it, then stop.

## Use this prompt shape

```text
Use the step-orchestrator skill with step source <table location>.
Process steps 3-5 in workspace <path>.
Run an implementer/reviewer loop until each step is approved.
Run tests: <commands>.
Constraints: <constraints>.
```
