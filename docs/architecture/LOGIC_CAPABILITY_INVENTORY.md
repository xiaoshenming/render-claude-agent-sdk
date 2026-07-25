# Logic Capability Inventory

This inventory fixes the ownership boundary for Tasks 6 and 7. The platform
reuses two frozen source lines; it does not create another Logic Agent.

## Runtime Mapping

| Capability | Frozen source | Platform owner | Task 6 status |
| --- | --- | --- | --- |
| Stateless Claude SDK self-review | `logic_self_audit_baseline` | `logic/reviewer.py` plus shared `agents/` runtime | Retained |
| Read-only tool and path policy | self-audit handoff | `agents/profile.py`, `agents/guards.py` | Retained and hardened |
| Strict structured issue output | self-audit handoff | `logic/output_schema.py`, `logic/_review_output.py` | Retained |
| Exact candidate citation binding | self-audit handoff | `logic/_citation_binding.py` | Retained and hash-bound |
| Blocked and human-review semantics | both source lines | `logic/schemas.py` | Corrected and fail-closed |
| Current-sample deterministic facts | `logic_engine_mvp_baseline` | `logic/engine_adapter.py` | Code-hash bound and recomputed before use |
| Bounded Scene/helper excerpts | `logic_engine_mvp_baseline` | `logic/engine_adapter.py` | Retained and sanitized |
| Malformed or truncated output safety | both source lines | SDK schema, runtime failure, `LogicReviewError` | Fail-closed; no guessed recovery |
| Incomplete or no-error issue filtering | `logic_engine_mvp_baseline` | structural invariants in `logic/schemas.py` | Retained without phrase rules |
| Frozen good/bad evaluation | both source lines | `logic/eval_manifest.py`, `logic/shadow.py`, `evals/` | Ready for shadow run |

## Deliberately Deferred To Task 7

The following existing capabilities are not part of the read-only Reviewer and
must be ported behind the Logic Coder boundary:

- repair contracts and multi-issue repair plans;
- Claude SDK Read/Edit execution;
- deterministic issue verifier and validator registry;
- diff scope checks, targeted render, and at-most-two repair attempts;
- duplicate patch and no-improvement circuit breakers.

Task 6 verifies the integrity of deterministic fact payloads against the exact
candidate code. Task 7 remains responsible for executing repair acceptance
predicates and deterministic post-patch validators before certification.

## Deliberately Excluded

- The historical DeepSeek reviewer is offline benchmark material only.
- The old CLI, run manager, report writer, settings, and secret loading are not
  production dependencies.
- Ground-truth labels, mutation metadata, external diagnoses, sample IDs, and
  repair hints are not passed to the Reviewer.
- A case manifest without a safe `scene_name` deliberately yields
  `current_sample_evidence.source = none`; diagnosis fields are not restored to
  make that field non-empty.
- The Reviewer cannot edit, certify, publish, or accept its own result.

## Packaging Boundary

The complete `logic_engine_mvp` snapshot remains frozen for provenance and
tests. The production wheel force-includes only `logic_facts.py`,
`review_input.py`, and side-effect-free package markers. A packaging regression
test prevents the legacy package initializer from pulling the old runtime back
into production.
