# Manim Quality Platform: Agent Engineering Contract

This file is the mandatory first read for every human or AI contributor.
It defines the non-negotiable Harness rules for this repository.

## Mission

Build an independent quality platform for generated Manim code. The platform
must improve production yield without allowing an Agent, SDK, checker, or
vendor package to certify its own output.

## Read Order

1. `AGENTS.md`
2. `docs/architecture/QUALITY_PLATFORM.md`
3. `docs/engineering/HARNESS.md`
4. The contract and tests for the module being changed

## System Boundary

- This repository is the only production implementation boundary for quality.
- Do not import `shuxuepai.apps`, `apps.render`, or another application repo.
- Generation and legacy render workers integrate through versioned contracts.
- Keep the first release a modular monolith. Split services only from measured
  throughput or isolation evidence.
- Preserve the overlap package as a verified frozen archive behind an adapter.
- Materialize it into ignored `.vendor/` storage only when tests or adapters need it;
  do not restore expanded vendor source to the active repository tree.

## Acceptance Authority

- Agents may review or propose edits. They never accept, promote, publish, or
  upload a revision.
- Only the Quality Orchestrator may change quality state.
- Every edit creates an immutable child revision.
- A failed candidate never overwrites a certified checkpoint.
- External checks must independently rerender and revalidate Agent output.
- SDK, checker, renderer, evidence, or budget failures never become PASS. Retry,
  regenerate, or hold remains a certification decision; the failure must not
  erase an earlier edited, executable best candidate. Preserve it as
  `candidate_risk` evidence until external policy decides its final state.

## Required Quality Flow

Every publish candidate follows this order:

1. Baseline revision and successful render
2. Mandatory read-only Logic Reviewer
3. Conditional Logic Coder and directed verification
4. Mandatory overlap detector
5. Conditional overlap Coder and external full recheck
6. Deterministic final consistency gate
7. Single idempotent publish

User modification previews may use targeted rendering. Approved modification
revisions must re-enter the complete flow above.

## Agent Tool Profiles

- Logic Reviewer: read-only, stateless, task workspace only.
- Logic Coder: Read and Edit, stateless, declared Scene scope only.
- Logic Verifier: read-only, stateless, frozen issue and diff only.
- Overlap Coder: Read and Edit, stateless, declared task workspace only.
- Deny Bash, arbitrary Write, Agent/Task, Web, upload, repository exploration,
  unlisted absolute paths, parent traversal, symlink escape, and junction escape.
- Canonical absolute paths are allowed only when they resolve inside the exact
  task-workspace allowlist. This keeps SDK Read/Edit calls deterministic on Windows.
- Tool and path allowlists must be enforced in code and hooks, not only prompts.

## Harness Budgets

- Budgets are centralized policy, never prompt-only suggestions.
- Bound context bytes, max turns, tool calls, wall time, per-call usage, stage
  usage, total job usage, repair attempts, and generated revisions.
- Do not start another Agent call when the remaining budget cannot cover it.
- Improvement may justify a policy route, but never bypass a hard platform cap.
- A repeated patch hash or repeated non-improving error fingerprint terminates
  the repair loop.

## Code Structure

- Target 200 lines per production file. Hard limit: 300 physical lines.
- Target 40 lines per function. Hard limit: 60 physical lines.
- Controllers, orchestrators, and runtimes coordinate; they do not contain
  prompts, storage implementations, validators, or vendor behavior.
- Prefer small Protocols, immutable models, adapters, explicit state machines,
  and structured result types with machine-readable reasons.
- Do not create universal `utils.py`, mutable cross-layer dictionaries, hidden
  singletons, or service locators.
- Allowed import direction is one-way: apps -> adapters -> ports -> domain ->
  contracts. Lower layers never import higher layers.
- Sibling feature packages communicate through contracts, not implementation
  imports.
- Generated files, migrations, schemas, and frozen vendor code require explicit
  path exceptions and must not be copied as patterns for new code.
- Remove duplication only when the shared abstraction has one stable owner.

## Testing And Evaluation

- Use test-driven development for behavior changes: failing test, minimal code,
  passing test, then refactor.
- Unit tests use fake SDK, renderer, detector, storage, and queue adapters.
- Network calls are forbidden in unit tests.
- Test clean, repair, warning, rollback, timeout, stale worker, duplicate task,
  evidence mismatch, and accepted-worse paths.
- Core acceptance, revision, runtime, and orchestrator modules require at least
  95% line coverage. The repository target is 85% line and 80% branch coverage.
- Prompt, model, validator, policy, tool, and schema versions are independent.

## Anti-Overfitting

- Never branch on sample IDs, titles, exact problem text, object names, or
  dataset directory names.
- A new rule needs a general invariant, a counterexample, a tuning-set test,
  and a frozen holdout result.
- Report performance on all attempted samples. Never hide unsupported cases.
- Keep known-good and known-bad holdouts frozen and separate from tuning data.

## Evidence And Observability

Each Agent call records model, prompt/schema/tool versions, input/output/cache
tokens, elapsed time, tool calls, structured output, patch, and error. Each
revision records parent, code hash, semantic fingerprint, affected Scenes,
render manifest, evidence versions, and acceptance reasons.

Final delivery binds code, per-Scene code hashes, slice hashes, assets, render
configuration, renderer version, Scene order, certificates, and video hash.

## Secrets And Data

- Secrets enter through controlled runtime configuration only.
- Never store secrets in source, prompts, logs, transcripts, fixtures, reports,
  archives, or evidence artifacts.
- Task workspaces are isolated. Do not read unrelated jobs or host paths.
- Evaluation manifests may reference external datasets by hash; do not duplicate
  large or sensitive datasets into this repository.

## Definition Of Done

A change is complete only when focused tests pass, engineering checks pass,
failure behavior is explicit, evidence is persisted, budgets are measured, and
the result is evaluated on the appropriate frozen holdout. Render success or an
Agent saying "fixed" is never completion evidence.
