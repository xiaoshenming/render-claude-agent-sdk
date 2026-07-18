# Logic Agent Reuse Correction

## Decision

The platform must not create a third Logic Agent. Task 6 and Task 7 reuse the
two already-proven source lines behind one platform adapter:

1. `logic_self_audit_agent_handoff_20260709` supplies the mandatory stateless
   Claude Agent SDK self-review behavior and structured issue contract.
2. `tools/logic_engine_mvp/logic_engine_mvp` supplies the later deterministic
   fact extraction, bounded review input, issue verification, repair contract,
   Claude SDK edit executor, validators, holdout guards, and round evidence.

The shared runtime in `src/manim_quality/agents/` is only the permission,
budget, usage, and audit boundary. It is not another Agent.

## Production Route

```text
QualitySubmission + immutable Revision
  -> deterministic facts and bounded current-sample evidence
  -> existing Claude SDK self-review Agent (Read only)
  -> issue/citation/provenance binding
  -> deterministic issue verification
  -> existing Claude SDK repair Agent when repairable (Read + Edit)
  -> validators and targeted render
  -> directed read-only verifier only for unresolved predicates
  -> Orchestrator certification
```

The historical DeepSeek chat-completion reviewer from `logic_engine_mvp` may be
used as an offline benchmark. It is not the mandatory production Reviewer and
must not become a second diagnosis source in the release path.

## Migration Rules

- Freeze and hash the latest `logic_engine_mvp` source before porting behavior.
- Write characterization tests for the existing public behaviors before edits.
- Preserve current-sample-only evidence and anti-hardcoding guards.
- Port reusable behavior into small platform modules; do not import the old CLI,
  run manager, report writer, or secret-bearing settings into production.
- Do not replace the existing self-review prompt silently. Every prompt or
  schema change requires a version, a stated invariant, known-good probes, and
  frozen known-bad evidence.
- Do not accept an Agent's self-reported success. Platform validators, render,
  and the Orchestrator remain authoritative.
- Keep overlap/aesthetic findings out of the logic contract.

## Capability Baseline

The file-level ownership map is frozen in
`docs/architecture/LOGIC_CAPABILITY_INVENTORY.md`.

Task 6 cannot be accepted until it proves that the adapter retains:

- stateless Claude SDK self-review with direct evidence;
- deterministic coordinate, distance, ratio, formula, angle, and relation facts
  supported by the latest source;
- bounded Scene/helper/visible-claim excerpts;
- strict issue completeness and no-error filtering;
- safe malformed/truncated output handling and human-review fallback;
- no sample-id, title, object-name, or dataset-directory branches.

Task 7 cannot be accepted until it proves that the adapter retains:

- Scene-bounded Claude SDK edits with Read + Edit only;
- deterministic repair contracts and validators;
- at most two attempts with duplicate/no-improvement circuit breakers;
- targeted render and external verification before certification.

## Evaluation Policy

For the current quality-first evaluation, the offline shadow runner may use a
higher model token ceiling than the commercial target. Every input, output,
cache, turn, tool, and latency metric remains recorded. Commercial token caps
and cheaper-model selection are decided in Task 13; they must not be simulated
by undercounting hidden reasoning tokens.

The first acceptance report uses all 30 frozen known-bad cases and all 6 frozen
known-good probes. Results must include errors and unsupported cases in the
denominator. No repair is enabled until Reviewer shadow output is stable.
