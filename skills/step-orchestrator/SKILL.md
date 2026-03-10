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
- Choose the step-table interaction path from the context already available in the session, such as installed skills, MCP tools, repository utilities, or built-in capabilities.
- Stop and report a blocker if the current context cannot safely inspect and update the named step table.

## Run the coordinator loop

- Inspect the source schema before mutating anything.
- Resolve the requested range against a sortable numeric or order field.
- Normalize duplicates and process steps in ascending order.
- Handle one step at a time. Do not overlap steps.
- For each step:
  1. Mark the step `In Progress`.
  2. Spawn implementer `A1` to change code for only that step. Instruct it not to commit, tag, or update the step table.
  3. Mark the step `In Review`.
  4. Spawn reviewer `B1` to review only that step. Keep reviewer read-only.
  5. If reviewer `B1` rejects the work, append `B1` review history, set the step back to `In Progress`, and spawn implementer `A2` with the review notes.
  6. Continue `A<n> -> B<n>` rounds until the reviewer approves or a hard blocker prevents safe progress.
  7. After approval, stage only the approved step's changes and commit `step {id}: {step_title}`.
  8. Mark the step `Done` and write back the approval summary plus commit SHA and message.
- Continue to the next requested step only after the current step is approved, committed, and written back.

## Keep side effects centralized

- Let implementer agents patch code and run the tests needed for that step.
- Let reviewer agents inspect and report findings, but never patch code.
- Let only the coordinator commit, update the step table, and decide whether a blocker is hard.

## Enforce the minimum contract

- Require one sortable numeric or order field for range resolution. Stop before mutation if it is missing.
- Infer a writable status field and map the local flow to `Todo`, `In Progress`, `In Review`, and `Done`. Stop before mutation if no writable status-like field exists.
- Infer notes and commit fields by name. If either field is missing, fall back to page-body or comment writeback instead of skipping the history.
- Append review history by round. Do not overwrite earlier `B1`, `B2`, or later reviewer feedback.
- Treat unsupported backends, missing required schema primitives, unrecoverable test or setup failures, or conflicting user changes as hard blockers. Write the blocker back when the backend allows it, then stop.

## Use this prompt shape

```text
Use the step-orchestrator skill with step source <table location>.
Process steps 3-5 in workspace <path>.
Run an implementer/reviewer loop until each step is approved.
Run tests: <commands>.
Constraints: <constraints>.
```
