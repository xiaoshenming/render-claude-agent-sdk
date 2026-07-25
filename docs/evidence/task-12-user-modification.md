# Task 12 User Modification Evidence

## Scope

Task 12 adds tenant-scoped user modification drafts, Scene-scoped SDK editing,
targeted previews, explicit approval/discard endpoints, and atomic re-entry into
the mandatory quality flow.

An accepted delivery remains terminal. Approval creates an immutable
`USER_MODIFICATION` audit revision plus a new child quality job whose baseline
is bound to the targeted preview manifest. The child queue payload is parsed
into the existing `ExecutionRequest`, so the existing Logic Reviewer, overlap
stage, final consistency gate, and idempotent delivery remain authoritative.

## RED to GREEN

- Initial RED: `ModuleNotFoundError: manim_quality.modification` from
  `tests/e2e/test_modification_preview_publish.py`.
- First GREEN: four AST Scene targeting and partial-application tests passed.
- Expanded GREEN: 23 focused modification tests passed.
- Repository-wide GREEN: 1173 passed, 4 skipped. The four skips are Windows
  symlink privilege limitations already tracked by the existing suite.

## Verified Invariants

- Agent execution uses the existing `AgentRuntime` and exact Coder
  `Read + Edit` profile. Bash, Write, Web, Task, and unlisted paths remain
  unavailable through the shared runtime guard.
- Scene membership/order, shared dependencies, unrequested Scenes, and every
  requested Scene are recomputed from AST evidence after the edit.
- A valid edit with failed preview is persisted as an immutable `FAILED` draft
  and cannot be approved.
- Idempotency conflicts are rejected before a second Agent call.
- Approval atomically writes the audit revision, child baseline/job,
  submission, quality queue item, and approved draft state.
- Injected approval failures roll back revision, child job, queue, and draft
  transition.
- SQLite behavior is executed end to end. PostgreSQL statement order,
  locking, transaction rollback, and migration shape are contract-tested.
- The original accepted job stays terminal; the child job starts at
  `BASELINE_READY` and runs the complete existing orchestrator.
- Preview manifest revision identity equals the child baseline revision
  identity.

## Review

Manual specification and code-quality review of the staged diff found and
fixed two blocking consistency gaps before approval:

1. Reopening `ACCEPTED` violated the frozen terminal-state contract. The design
   now creates a child quality job.
2. The first child baseline used a preview manifest bound to another revision.
   Preview and child baseline identities are now identical.

Three time-bounded read-only reviewer attempts did not inspect the staged diff
before their execution limit and were stopped under the team timeout policy.
Their lack of output is not counted as approval. Main-thread review and the
machine gates are the available Task 12 review evidence.

## Residual Validation

Task 14 must still run:

- migration `0004_user_modifications.sql` against live PostgreSQL;
- concurrent identical/conflicting draft creation and approval;
- connection loss at every approval transaction boundary;
- real Claude Agent SDK user-modification holdout intent fulfillment and
  regression measurement;
- blind before/after preview review;
- end-to-end integration with the production generation artifact/context
  provider.

Until those checks pass, Task 12 is implementation-complete but not a claim of
production launch certification.
