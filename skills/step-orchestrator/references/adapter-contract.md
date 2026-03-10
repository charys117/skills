# Adapter Contract

Use this contract when checking whether a step-table backend is safe to drive.
Choose the concrete interaction method from the current session context rather than assuming one integration.

## Resolve the source

- Normalize the user-provided source to one stable table or database identifier.
- Confirm that the backend supports reading rows or pages and updating at least status plus one notes sink.
- Inspect the schema before mutating anything.
- Reuse an available skill, MCP, CLI, or repository utility when one already matches the backend. Do not introduce a new backend-specific dependency just for this skill.

## Resolve the requested steps

- Require one sortable numeric or order field. Common names include `Step`, `ID`, `Order`, `Seq`, and `Number`.
- Parse comma-separated single values and closed ranges.
- Expand `3-5,7` to `3,4,5,7`, deduplicate the result, and sort it ascending.
- Match requested values against the numeric or order field and stop if any requested step is missing.

## Infer fields

- Use the backend title or name field as the step title and commit subject.
- Infer status from fields such as `Status`, `State`, or `Step Status`.
- Infer review notes from fields such as `Review Notes`, `Acceptance Notes`, `QA Notes`, or `Notes`.
- Infer commit metadata from fields such as `Commit`, `Git Commit`, `Commit SHA`, or `Git SHA`.
- Treat missing notes or commit fields as non-fatal only when the backend supports page-body or comment fallback.
- Treat missing numeric or order fields and missing writable status fields as hard blockers.

## Apply the state machine

| Moment | Required writeback |
| --- | --- |
| Start work | `Status = In Progress` |
| Hand to reviewer | `Status = In Review` |
| Reviewer rejects | Append `B<n>` rejection notes and set `Status = In Progress` |
| Reviewer approves | Append `B<n>` approval notes |
| Finish step | Commit `step {id}: {step_title}`, set `Status = Done`, and store commit SHA and message |

## Format review history

Append chronological Markdown-compatible entries:

```text
### B1 rejected
Summary: <short verdict>
Required changes: <actionable list>

### B2 approved
Summary: <why it passed>
```

Reuse the same content in a comment or page-body fallback when dedicated notes fields are missing.

## Treat these conditions as hard blockers

- Unsupported backend or unknown mutation path
- Backend exists but the current session has no safe way to inspect and update it
- Missing numeric or order field
- Missing writable status field
- Unrecoverable test or environment failure
- Conflicting user changes that make the current step unsafe to continue
- Requested step ID that does not exist in the resolved table
