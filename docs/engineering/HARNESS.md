# Harness Engineering Standard

## Purpose

The Harness is the controlled environment around model calls. Claude Agent SDK
provides a capable execution substrate, but platform reliability comes from the
contracts, permissions, state, checks, rollback, and evidence surrounding it.

## Core Principle

The model understands and edits. The Harness scopes, executes, measures,
validates, accepts, rolls back, and publishes.

No component may both produce a candidate change and grant final acceptance to
that same change.

Candidate retention and final certification are separate decisions. Once an
Agent has produced an edited, executable candidate, SDK turn exhaustion,
structured-output formatting, citation drift, or a later failed attempt may add
risk evidence but must not erase the best previously observed candidate.

## Responsibilities

### Agent Runtime

- Creates an isolated workspace for one job and one role.
- Loads a versioned role profile and output schema.
- Enforces tool, path, turn, time, and usage budgets.
- Captures the complete structured transcript and usage record.
- Returns a candidate result. It never updates certification state.

### Quality Orchestrator

- Owns the persisted state machine and stage checkpoints.
- Starts bounded Agent and deterministic tool calls.
- Creates immutable candidate revisions.
- Applies external acceptance policy.
- Promotes, rejects, rolls back, regenerates, holds, or publishes.

### Deterministic Tools

- Compile and render declared Scenes.
- Extract facts and run validators.
- Detect and classify overlap.
- Verify diff scope and semantic fingerprints.
- Bind code, slices, assets, configuration, evidence, and video versions.

### Vendor Packages

- Return evidence and candidate patches only.
- Remain frozen and hash-pinned behind platform adapters.
- Do not own platform state, retry, acceptance, or publishing.

## Role Isolation

Reviewer, Coder, and Verifier use separate stateless sessions. The Coder gets a
frozen issue and edit scope, not the Reviewer's free-form reasoning history. A
Verifier sees the original requirement, frozen issue, complete candidate source,
candidate diff, and changed Scene evidence. It reports every frozen issue as
`resolved`, `unresolved`, or `unknown`; citation metadata helps diagnosis but is
not an acceptance gate by itself.

## Tool Security

Production role profiles use an explicit allowlist and deny-by-default hooks.
Read and Edit paths must resolve inside the task workspace after following links.
Allow canonical absolute paths only when they resolve inside the exact workspace
allowlist. Reject all other absolute paths, parent traversal, alternate data
streams, symlinks, and junctions that escape the workspace.

Do not expose shell access as a convenience. Rendering, checking, and evidence
queries are typed platform services called by the Orchestrator. If a structured
check tool is later exposed to a role, the platform still repeats the check
outside the Agent session.

## Revisions And Checkpoints

Never mutate a certified revision. Candidate revisions have a parent and one
declared stage. Track these independent checkpoints:

- render baseline
- logic certified
- layout certified
- delivery

Each Scene entry binds its code hash, slice hash, assets, render configuration,
renderer version, and order. A total file hash alone is insufficient when slices
are reused.

## Logic Flow

1. Run the read-only Logic Reviewer for every publish candidate.
2. Treat PASS as "no evidenced blocker found", not mathematical proof.
3. `RECORD_ONLY` has no acceptance meaning.
4. Route only low-severity, low-impact, evidence-complete observations to the
   warning policy.
5. Route possible answer, geometry, or teaching errors that cannot be verified
   to regenerate or hold.
6. Freeze repair issues and acceptance predicates before calling the Coder.
7. After a patch, run AST/diff scope checks, compile, affected-Scene render,
   deterministic validators, and a changed-Scene risk scan.
8. Use a directed read-only Verifier only when deterministic validation is not
   sufficient.
9. Preserve the best edited candidate across attempts. A later SDK, parser,
   citation, or Verifier failure marks risk and falls back to that candidate,
   not automatically to the original known-bad source.
10. Final certification still belongs to external policy. Preserving a
    `candidate_risk` revision does not silently turn it into PASS.

## Layout Flow

1. Run the detector on every logic-certified revision.
2. Call the overlap Coder only for blocking issues.
3. Treat vendor clean/degraded statuses as candidate evidence, not acceptance.
4. Rerender affected Scenes and run the complete external overlap check.
5. Reject semantic fingerprint changes from a layout-only patch.
6. Promote only under platform residual-risk policy.

## Bounded Execution

Repair attempts are limited by role and job policy. The default architecture
allows at most two logic repairs, two overlap repairs, and three Agent-generated
revisions per job. The policy may be tightened by tenant or queue but not loosened
inside prompts.

The current MathPi logic replay profile uses 12 Coder turns, 8 Verifier turns,
and 64 total tool calls as bounded soft budgets. Exhaustion stops further work
and records risk; it does not discard an already edited best candidate.

Persist a stage run ID, lease owner, heartbeat, deadline, retry budget, and
terminal state. Infrastructure failures cannot cause infinite queue retries.

## Cost Control

Use separate fast, standard-repair, high-risk, and exception queues. All jobs run
the mandatory Reviewer and detector. Expensive second attempts, full-context
fallbacks, or directed Verifiers are limited to evidence-backed high-risk paths.

Measure cost per role and per delivered job. Report high-risk tails separately;
an average must not hide a small group of unbounded jobs.

## Performance

- Index Scenes before reading full bodies.
- Read only relevant Scene bodies for ordinary review.
- Rerender only affected Scenes and reuse unchanged certified slices.
- Compute affected Scenes from AST and dependency evidence, not Agent claims.
  Changes to shared helpers, BaseConfig, global constants, assets, Scene order,
  or any dependency with uncertain impact require a complete rerender.
- Cache deterministic facts by revision and tool version.
- Stop on repeated patches, repeated errors, no improvement, or exhausted budget.
- Consider speculative baseline overlap detection only after the serial flow is
  correct; invalidate its evidence when logic changes the revision.

## Quality Evidence

Architecture is not proof of quality. Release decisions require frozen,
independent evidence:

- known-good logic set for false positives and over-edit rate
- known-bad logic set for precision, recall, and repair success
- frame-annotated overlap set for detector recall and repair outcome
- user modification set for intent fulfillment and regression rate
- before/after video blind review for correctness and readability
- load and failure-injection runs for state correctness and latency

Video aesthetics, pacing, narration, and visual richness are not automatically
improved by logic or overlap repair. Add a separate versioned quality module only
after its rubric and holdout are defined.

## Machine Gates

The foundation CI enforces formatting, lint, production file/function limits,
legacy-import isolation, and tests. Before production modules are enabled, CI
must also enforce strict typing, unit/integration coverage, dependency rules,
and secret scanning. Frozen vendor and generated files require explicit root
exceptions and provenance hashes; arbitrary directory names never bypass checks.

## Required Release Metrics

- critical logic recall and overall logic precision
- known-good over-edit rate
- logic repair success rate
- overlap detector recall and blocking clear rate
- accepted-worse rate
- sampled delivered-video good rate
- automatic delivery rate
- token and latency distributions by role and route
- stale evidence, duplicate publish, and revision mismatch counts

Targets live in versioned commercial policy, not in prompts or this document.
