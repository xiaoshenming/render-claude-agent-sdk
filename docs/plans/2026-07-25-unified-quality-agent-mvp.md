# Unified Quality Agent MVP Implementation Plan

> **Route update (2026-07-25):** The implemented and supported route is now one
> parent Quality Agent plus two native foreground Reviewer subagents,
> Solution-only model context, seven structured tools, bounded patches, and
> external acceptance gates. The original eight-tool/single-Agent slices below
> are retained only as historical design context and must not be used as the
> deployment contract. See `docs/unified-quality-agent-mvp.md`.

- Date: 2026-07-25
- Branch: `codex/unified-quality-agent-mvp`
- Baseline: `18a94aed86047f2069eb1b9d277cbfdf2e1f8980`
- Status: implemented; awaiting real Manim adapters and samples

## 1. Goal

Build the smallest production-shaped MVP in which one Claude Agent SDK session
can inspect a rendered Manim candidate, diagnose mathematical or visual-logic
defects, make a bounded logic patch, inspect overlap facts, make a separate
layout patch, and submit a candidate to the outer Harness.

The MVP proves or disproves one question:

> Does one capable, well-tooled Agent retain enough context to repair both
> logic and layout more reliably than the current handoff between separate
> Reviewer and Coder calls, without giving the Agent acceptance authority?

## 2. Non-Negotiable Boundaries

- The Agent reads the locked problem statement, explanation, and Manim source
  directly. `LogicEvidence` and `ReviewDigest` are not required by this route.
- The Agent receives only registered structured tools. Bash, arbitrary Write,
  Web, Skill, sub-Agent, repository exploration, and unrestricted paths remain
  denied.
- The original `R0` source and problem hash are immutable.
- Logic and layout edits are separate revisions. One patch cannot claim both
  scopes.
- The Agent may request validation and may submit a candidate. It cannot
  certify, promote, publish, or overwrite a checkpoint.
- The outer Harness independently reruns compile, render, logic checks, overlap
  checks, scope guards, and consistency gates.
- At most two accepted patch attempts are allowed. Duplicate patches,
  non-improving validation fingerprints, problem changes, content deletion, or
  scope violations stop the run.
- No code may branch on sample IDs, exact titles, exact problem text, dataset
  paths, or special Manim object names.

## 3. Tool Surface

The unified Agent receives exactly these versioned capabilities:

1. `read_problem`
   - Returns immutable problem/explanation source and its hash.
2. `read_candidate`
   - Returns the current candidate revision or a bounded line range.
3. `check_relation`
   - Runs a deterministic numeric, symbolic, or geometry relation adapter.
4. `record_findings`
   - Freezes structured issues and their validation criteria before editing.
5. `apply_patch`
   - Applies one exact replacement patch to the current candidate and creates a
     child revision with either `logic` or `layout` scope.
6. `inspect_layout`
   - Runs the registered overlap detector against the current revision.
7. `validate_revision`
   - Runs bounded external checks and returns facts to the Agent. It does not
     accept the revision.
8. `submit_revision`
   - Ends the Agent session with a candidate revision ID and declared findings.
     The outer Harness still decides PASS, HOLD, or rollback.

## 4. Runtime Design

### 4.1 Managed Tools

Generalize the current read-only MCP grant into an audited managed-tool grant.
Each grant declares:

- safe server and tool names;
- JSON input schema and optional semantic validator;
- synchronous handler;
- read-only or mutating effect;
- call limit, timeout, and maximum result size;
- structured result hash for audit.

The existing geometry read tool remains source compatible.

### 4.2 Tool Broker

One per-run broker owns all mutable session state:

- immutable problem snapshot and hash;
- immutable `R0`;
- current revision and revision history;
- frozen findings;
- patch hashes and validation fingerprints;
- remaining patch attempts;
- submitted revision ID.

Handlers can only access this broker. They do not receive a filesystem path from
the model.

### 4.3 SDK Operator

`QualityOperatorAgent` builds one stateless Claude SDK request with:

- an operator profile with no built-in tools;
- the eight managed MCP tools;
- a compact phase-oriented prompt;
- a strict terminal output schema;
- centralized token, turn, tool-call, and wall-time budgets.

The prompt describes invariants, not sample-specific repair recipes.

## 5. Revision Flow

```text
R0 baseline
  |
  +-- logic patch --> R1 LOGIC_REPAIR / SCENE_LOGIC
                         |
                         +-- external validation feedback
                         |
                         +-- layout patch --> R2 LAYOUT_REPAIR / LAYOUT_ONLY
                                                |
                                                +-- external validation feedback
```

Rules:

- A layout revision may only descend from the current logic candidate.
- A second logic patch may descend from the first logic candidate only when the
  previous validation improved.
- A second layout patch follows the same improvement rule.
- A layout patch that changes semantic fingerprint is rejected.
- A failed child never replaces its parent or the certified checkpoint.

## 6. Outer Acceptance

After `submit_revision`, a separate MVP gate:

1. verifies problem hash and revision ancestry;
2. compiles the source;
3. rerenders through the injected renderer;
4. runs directed logic validation for recorded blocking issues;
5. runs the full overlap detector;
6. enforces patch scope and semantic-fingerprint rules;
7. returns a proposed candidate or rolls back to `R0`.

No Agent output field can bypass this gate.

The MVP gate deliberately cannot emit platform `ACCEPTED`. Production delivery
must still persist the proposed revision and pass the existing final
consistency gate, repository transition, and delivery-certificate flow.

## 7. Delivery Slices

### Slice A: Runtime Capability Layer

- Add failing tests for managed custom tools, call limits, timeout, result
  auditing, mutating-tool denial, and SDK registration.
- Implement the managed grant while preserving current read-tool behavior.

### Slice B: Session And Revisions

- Add failing tests for immutable `R0`, locked problem hash, findings-before-
  patch, separate logic/layout revisions, duplicate patch rejection, and
  non-improving retry termination.
- Implement the per-run broker and immutable revision artifacts.

### Slice C: Eight Tools

- Add contract tests for every tool.
- Implement handlers over injected relation, layout, and validation ports.
- Ensure model inputs never contain arbitrary host paths.

### Slice D: Unified SDK Agent

- Add fake-SDK tests for the intended tool sequence, missing findings,
  over-budget runs, invalid submission, and failure-close behavior.
- Implement prompt, schema, profile, and operator facade.

### Slice E: Outer Gate And CLI

- Add tests proving that Agent self-reports cannot accept a bad candidate.
- Implement a single-task CLI that creates an isolated workspace, runs the
  operator, executes the outer gate, and persists JSONL audit artifacts.

### Slice F: Verification

- Run focused tests after each red-green cycle.
- Run full pytest and Ruff.
- Record the two pre-existing frozen-source failures separately.
- Run a network-free fake end-to-end case before accepting real user code.

## 8. MVP Output Contract

Each run persists:

```text
run/
  input/
    problem.snapshot
    candidate.R0.py
  revisions/
    R1.logic.py
    R2.layout.py
  evidence/
    findings.json
    validation.<revision>.json
    layout.<revision>.json
  logs/
    agent_call.json
    tool_calls.jsonl
    run_summary.json
  output/
    proposed_candidate.py
    decision.json
```

Files are written by the Harness, not by arbitrary model-selected paths.

## 9. Completion Criteria

The MVP is ready for the user's real code only when:

- all eight tools execute through Claude Agent SDK in one session;
- no denied built-in capability is exposed;
- tests prove `R0` and problem hash cannot change;
- tests prove logic/layout revisions cannot be merged;
- tests prove outer validation can reject an Agent-submitted candidate;
- focused tests and Ruff pass;
- full-suite results are no worse than the recorded baseline, excluding the two
  known frozen-source hash failures;
- a local fake end-to-end run produces auditable revisions and a final decision.

## 10. Verification Record

Verified on 2026-07-25:

- focused Operator, Agent runtime, repair-boundary, and SDK integration:
  `148 passed, 1 skipped`;
- engineering standards: `9 passed`;
- Ruff: passed;
- final full suite: `1421 passed, 2 failed, 4 skipped`;
- the two failures are unchanged baseline integrity failures in
  `test_holdout_runner.py` and `test_source_provenance.py`;
- independent read-only review found no internal blocking defect.

Real Manim rendering and overlap detection remain intentionally unbound until
the user provides the complete candidate and runtime command. The compile-only
CLI always returns `HOLD`; it is not the production entrypoint.
