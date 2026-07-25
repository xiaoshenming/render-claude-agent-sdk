# Manim Commercial Quality Platform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an independent commercial-grade Manim quality delivery platform that accepts generated code/render artifacts, runs mandatory logic Agent review, conditionally runs overlap repair, supports bounded repair loops and user modifications, and returns a versioned quality-certified result.

**Architecture:** Create a Python 3.11 modular monolith with a persisted quality state machine. Keep generation outside the workspace behind an ingestion contract. Reuse the current overlap handoff package through an adapter, productionize the existing self-audit logic Agent as separate reviewer/coder/verifier roles, and make the platform orchestrator the only component allowed to accept revisions or publish results.

**Tech Stack:** Python 3.11, FastAPI, PostgreSQL, RabbitMQ, S3/COS-compatible object storage, Claude Agent SDK, pytest, Docker Compose; optional React/TypeScript workbench after the backend MVP.

---

## 1. Fixed Decisions

- New independent workspace: `D:\manim_quality_platform`.
- The generation engine is not copied into this workspace.
- Generation integrates later through `QualitySubmission` and an optional `GenerationAdapter`.
- Logic Reviewer Agent runs for every renderable candidate.
- Overlap detector runs for every logic-certified revision.
- Overlap repair Agent runs only when blocking overlap is detected.
- Agent output never has acceptance authority.
- Every edit creates a new immutable revision.
- All repair loops are bounded and progress-driven.
- Final consistency validation is deterministic and has no LLM call.
- Only low-severity, low-impact, evidence-complete observations allowed by versioned policy may produce `ACCEPT_WITH_WARNING`; low confidence alone is never sufficient.
- The first release is a modular monolith, not microservices.

## 2. Source Components To Migrate

### 2.1 Overlap repair

Source archive:

```text
C:\Users\Admin\Desktop\quality_repair_source_handoff_20260710.tar.gz
```

Frozen archive and generated materialization target:

```text
vendor/source_archives/quality_repair_source_handoff_20260710.tar.gz
.vendor/quality_repair/
```

Migration policy:

- Preserve source provenance and package tests.
- Keep expanded vendor source out of the active Git tree; verify and materialize
  the archive only when tests or the adapter require it.
- Do not merge its internal controller into the platform orchestrator.
- Wrap public `repair(bundle, toolbox)` in `OverlapRepairAdapter`.
- Treat package `SUCCESS_DEGRADED` as a candidate result, not automatic platform acceptance.
- Enforce platform-level token budget because the package's current progress policy can exceed its nominal token cap.
- Always run external render and overlap recheck before accepting its output.

### 2.2 Logic self-audit Agent

Primary self-review source:

```text
C:\Users\Admin\Desktop\shuxuepai\apps\render\app\workers\post_render_logic
C:\Users\Admin\Desktop\逻辑工具\logic_self_audit_agent_handoff_20260709
```

Latest logic-engine source:

```text
C:\Users\Admin\Desktop\shuxuepai\tools\logic_engine_mvp\logic_engine_mvp
```

Target location:

```text
src/manim_quality/logic/
```

Reuse:

- The existing stateless Claude Agent SDK self-review behavior and structured
  issue contract from the primary source.
- Deterministic fact extraction, bounded review input, issue verification,
  repair contracts, SDK edit execution, validators, holdout guards and round
  evidence from the latest logic-engine source.
- Platform revision/render binding, permissions and audit around those existing
  capabilities.

Do not create a third Logic Agent. The historical chat-completion reviewer in
`logic_engine_mvp` is an offline benchmark only; the mandatory production
Reviewer remains the Claude Agent SDK self-review Agent. See
`docs/plans/2026-07-10-logic-agent-reuse-correction.md`.

Do not copy unchanged:

- PASS when issues are empty regardless of blocked/human state.
- One-issue-only planning.
- Literal string replacement as the only repair method.
- `text_present/text_absent` as the only recheck.
- Hard-coded scope compliance.
- Disabled new-risk scan.

### 2.3 Existing modification flow

Source:

```text
C:\Users\Admin\Desktop\shuxuepai\apps\render\app\workers\modify
```

Target concepts:

- Scene targeting.
- Re-render only affected slices.
- Reuse unchanged slices.
- Final concatenation.

Do not preserve silent partial success. Failed user-requested changes must remain draft failures unless the user explicitly accepts partial application.

## 3. Target Workspace

```text
D:\manim_quality_platform\
├── pyproject.toml
├── README.md
├── .env.example
├── docker-compose.yml
├── packages/
│   └── quality_repair/              # preserved overlap package
├── src/manim_quality/
│   ├── contracts/                   # public requests, results, states, certificates
│   ├── orchestrator/                # persisted bounded state machine
│   ├── revisions/                   # immutable code/render/evidence revisions
│   ├── agents/                      # shared Claude SDK runtime and profiles
│   ├── logic/                       # reviewer, coder, verifier, validators
│   ├── layout/                      # detector and quality_repair adapter
│   ├── modification/                # user intent planner and edit Agent
│   ├── rendering/                   # render/concat/frame Protocol adapters
│   ├── delivery/                    # final gate and result certificate
│   ├── storage/                     # PostgreSQL and object storage adapters
│   └── observability/               # metrics, traces, token accounting
├── apps/
│   ├── api/                         # FastAPI control plane
│   ├── worker/                      # RabbitMQ consumer
│   └── web/                         # commercial workbench, later phase
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   ├── failure_injection/
│   └── fixtures/
├── evals/
│   ├── logic_known_bad/
│   ├── logic_known_bad_replacement/
│   ├── logic_known_good/
│   ├── logic_holdout/
│   ├── overlap_holdout/
│   └── modification_holdout/
├── migrations/
├── docs/
└── scripts/
```

## 4. Public Contracts

### Quality submission

```python
@dataclass(frozen=True, slots=True)
class QualitySubmission:
    job_id: str
    tenant_id: str
    candidate_code_ref: str
    problem_text: str
    planning: dict[str, object]
    expected_answer: str | None
    render_manifest_ref: str | None
    asset_manifest_ref: str | None
    callback_url: str | None
    idempotency_key: str
```

### Revision

```python
@dataclass(frozen=True, slots=True)
class Revision:
    revision_id: str
    parent_revision_id: str | None
    code_hash: str
    semantic_fingerprint: str
    render_manifest_hash: str | None
    changed_scene_ids: tuple[str, ...]
    patch_scope: str
    created_by: str
    attempt: int
```

### Quality result

```python
class DeliveryDecision(StrEnum):
    ACCEPT = "ACCEPT"
    ACCEPT_WITH_WARNING = "ACCEPT_WITH_WARNING"
    REGENERATE = "REGENERATE"
    HOLD = "HOLD"
    FAILED = "FAILED"

@dataclass(frozen=True, slots=True)
class QualityResult:
    job_id: str
    decision: DeliveryDecision
    accepted_revision_id: str | None
    final_code_ref: str | None
    final_render_manifest_ref: str | None
    certificate_ref: str
    warnings: tuple[str, ...]
    token_usage: dict[str, int]
    timings_ms: dict[str, int]
```

### Generation adapter, reserved for later integration

```python
class GenerationAdapter(Protocol):
    async def regenerate(
        self,
        submission: QualitySubmission,
        failure_evidence_ref: str,
    ) -> QualitySubmission: ...
```

The platform must run without this adapter. When it is absent, `REGENERATE` is returned to the caller instead of invoking generation internally.

## 5. Persisted State Machine

```text
RECEIVED
→ INPUT_VALIDATED
→ BASELINE_READY
→ LOGIC_REVIEWING
  ├─ PASS → LOGIC_CERTIFIED
  ├─ LOW_RISK_WARNING + POLICY_PASS → LOGIC_CERTIFIED_WITH_WARNING
  ├─ RECORD_ONLY → POLICY_EVALUATING
  ├─ REPAIR → LOGIC_REPAIRING
  └─ HUMAN / BLOCKED → REGENERATE_OR_HOLD
→ LOGIC_VERIFYING
  ├─ PASS → LOGIC_CERTIFIED
  ├─ IMPROVED + BUDGET → LOGIC_REPAIRING
  └─ FAIL → REGENERATE_OR_HOLD
→ LAYOUT_CHECKING
  ├─ CLEAN → LAYOUT_CERTIFIED
  └─ BLOCKING → LAYOUT_REPAIRING
→ LAYOUT_VERIFYING
  ├─ CLEAN → LAYOUT_CERTIFIED
  ├─ ALLOWED_WARNING → LAYOUT_CERTIFIED_WITH_WARNING
  └─ FAIL → REGENERATE_OR_HOLD
→ FINAL_CONSISTENCY_GATE
→ ACCEPTED / ACCEPTED_WITH_WARNING / REGENERATE / HOLD / FAILED
```

Global limits:

- Logic repair attempts: 2.
- Overlap repair attempts: 2.
- Agent-produced revisions: 3 total.
- Identical patch hash: never execute twice.
- No-progress error signature: stop after one repeated non-improving result.
- Platform quality Agent token budget: target 60k/job, absolute policy ceiling configurable per tenant.

## 6. Implementation Tasks

### Task 0: Establish the Harness engineering contract

**Files:**

- Create: `D:\manim_quality_platform\AGENTS.md`
- Create: `D:\manim_quality_platform\docs\engineering\HARNESS.md`
- Create: `D:\manim_quality_platform\scripts\check_engineering_standards.py`
- Test: `D:\manim_quality_platform\tests\engineering\test_engineering_standards.py`

**Steps:**

1. Make the independent workspace the only production implementation boundary; forbid direct `apps.*` imports from the old repository.
2. Define one-way module dependencies, Agent tool permissions, immutable revision ownership, external acceptance and fail-closed behavior.
3. Add machine checks for production file length, function length and explicit vendor/generated exceptions.
4. Require test-first changes, structured reasons, frozen holdout evaluation and anti-case-hardcoding checks.
5. Run the engineering tests before migrating either source package.

### Task 1: Initialize the independent workspace

**Files:**

- Create: `D:\manim_quality_platform\pyproject.toml`
- Create: `D:\manim_quality_platform\README.md`
- Create: `D:\manim_quality_platform\.gitignore`
- Create: `D:\manim_quality_platform\src\manim_quality\__init__.py`
- Create: `D:\manim_quality_platform\tests\unit\test_imports.py`

**Steps:**

1. Create a Python 3.11 virtual environment.
2. Write an import smoke test for `manim_quality`.
3. Run the test and confirm it fails before the package exists.
4. Add the package skeleton and minimal `pyproject.toml`.
5. Run `python -m pytest tests/unit/test_imports.py -q` and confirm PASS.
6. Initialize Git and commit only the workspace skeleton.

### Task 2: Freeze and verify source packages

**Files:**

- Create: `vendor/source_archives/quality_repair_source_handoff_20260710.tar.gz`
- Create: `scripts/materialize_quality_repair.py`
- Create: `docs/source-provenance.md`
- Create: `scripts/verify_vendor_sources.py`
- Test: `tests/unit/test_source_provenance.py`

**Steps:**

1. Add a failing test requiring overlap source commit, archive SHA-256, SDK version and test command.
2. Verify the archive and its embedded manifests without extracting into Git.
3. Materialize into ignored `.vendor/` storage and run its Linux/Python 3.11
   `verify_handoff.sh`.
4. Record the result and known Windows incompatibilities separately.
5. Copy only the logic self-audit source and tests into a staging directory; do not import it into production modules yet.
6. Run the existing 27-test logic baseline.
7. Commit source provenance and frozen baselines.

### Task 3: Implement public contracts and state transitions

**Files:**

- Create: `src/manim_quality/contracts/submission.py`
- Create: `src/manim_quality/contracts/revision.py`
- Create: `src/manim_quality/contracts/result.py`
- Create: `src/manim_quality/contracts/state.py`
- Test: `tests/unit/contracts/`

**Steps:**

1. Write failing serialization and invalid-transition tests.
2. Implement immutable dataclasses and enums.
3. Implement an explicit transition table; reject unlisted transitions.
4. Require `schema_version` in all persisted JSON.
5. Run `python -m pytest tests/unit/contracts -q`.
6. Commit contracts separately from orchestration behavior.

### Task 4: Build immutable revision and artifact storage

**Files:**

- Create: `src/manim_quality/revisions/store.py`
- Create: `src/manim_quality/revisions/fingerprint.py`
- Create: `src/manim_quality/storage/artifacts.py`
- Create: `src/manim_quality/storage/database.py`
- Create: `migrations/0001_quality_core.sql`
- Test: `tests/unit/revisions/`
- Test: `tests/integration/test_revision_repository.py`

**Steps:**

1. Write tests proving revisions cannot be overwritten.
2. Add SHA-256 code, render and evidence hashing.
3. Add AST-based semantic fingerprint placeholders for strings, geometry definitions and animation ordering.
4. Add stage checkpoints (`render_baseline_revision_id`, `logic_certified_revision_id`, `layout_certified_revision_id`, `delivery_revision_id`) and optimistic version fields.
5. Add idempotent artifact writes.
6. Verify that a stale worker cannot replace a newer revision.
7. Commit revision infrastructure.

### Task 5: Build the shared Agent Runtime

**Files:**

- Create: `src/manim_quality/agents/runtime.py`
- Create: `src/manim_quality/agents/profile.py`
- Create: `src/manim_quality/agents/budget.py`
- Create: `src/manim_quality/agents/guards.py`
- Create: `src/manim_quality/agents/usage.py`
- Test: `tests/unit/agents/`

**Steps:**

1. Write tests for allowed tools, path isolation, max turns and token accounting.
2. Implement profiles for read-only reviewer and Read/Edit coder.
3. Deny Bash, Write, Agent, Task, Web, arbitrary directories and upload tools.
4. Enforce a true pre-call and pre-next-round budget; improvement must not bypass the platform ceiling.
5. Persist prompt, structured output, tool calls, input/output/cache tokens and elapsed time.
6. Add duplicate-read and duplicate-patch detection.
7. Run fake-SDK tests without network.
8. Commit the runtime independently.

### Task 6: Productionize the Logic Reviewer

**Files:**

- Create: `src/manim_quality/logic/evidence.py`
- Create: `src/manim_quality/logic/reviewer.py`
- Create: `src/manim_quality/logic/schemas.py`
- Create: `src/manim_quality/logic/prompts/reviewer.md`
- Test: `tests/unit/logic/test_reviewer.py`
- Eval: `evals/logic_known_bad/`, `evals/logic_known_bad_replacement/`,
  `evals/logic_known_good/`

**Steps:**

1. Freeze and verify the latest `logic_engine_mvp` source and write a capability
   inventory against the self-audit handoff.
2. Write characterization tests for the existing self-review Agent before
   changing prompts, schemas or evidence.
3. Port current-sample evidence, deterministic facts and bounded Scene/helper
   excerpts without `apps.*` imports or the old CLI/run manager.
4. Add problem, planning, expected answer provenance and render manifest binding.
5. Fix blocked/human-review semantics before PASS and retain malformed-output,
   incomplete-issue and no-error filtering behavior.
6. Require direct evidence for every issue and deterministic verification for
   every computable claim.
7. Keep the existing Claude SDK review read-only and stateless; do not introduce
   a second production Reviewer.
8. Run all frozen known-bad and known-good probes and produce a shadow report
   before enabling any repair.
9. Commit source freeze, Reviewer adapter and evaluation harness separately.

### Task 7: Implement Logic Coder, validators and directed verifier

**Files:**

- Create: `src/manim_quality/logic/coder.py`
- Create: `src/manim_quality/logic/repair_plan.py`
- Create: `src/manim_quality/logic/validators/registry.py`
- Create: `src/manim_quality/logic/verifier.py`
- Create: `src/manim_quality/logic/diff_guard.py`
- Test: `tests/unit/logic/test_coder.py`
- Test: `tests/integration/test_logic_repair_flow.py`

**Steps:**

1. Characterize and port the existing `logic_engine_mvp` repair contract,
   Claude SDK edit executor and validators instead of creating a new Coder.
2. Write tests for multiple issues and Scene-scoped edit plans.
3. Preserve Read + Edit only and extend literal repair to guarded Scene-level
   Edit without importing the old CLI or secret-bearing settings.
4. Add compile, AST scope, expected-answer, formula, coordinate and geometry
   validators, reusing the verified deterministic implementations.
5. Add a read-only directed Verifier only for predicates that deterministic
   validators cannot resolve.
6. Re-scan changed Scene risk; do not mark scope compliance as a constant.
7. Limit repair to two attempts and require measurable evidence before attempt two.
8. Run known-bad and known-good evals and save token/latency metrics.
9. Commit logic repair only after reviewer shadow output is stable.

### Task 8: Integrate the overlap repair package

**Files:**

- Create: `src/manim_quality/layout/adapter.py`
- Create: `src/manim_quality/layout/policy.py`
- Create: `src/manim_quality/layout/result_mapping.py`
- Test: `tests/integration/test_overlap_adapter.py`

**Steps:**

1. Write a failing adapter test using the package's stub checker.
2. Materialize the verified archive into isolated runtime storage.
3. Map platform candidate artifacts to `RepairBundle` and `ToolBox`.
4. Preserve package evidence directory and token usage.
5. Map `SUCCESS_CLEAN` to a candidate requiring external render/recheck.
6. Map `SUCCESS_DEGRADED` through platform residual-risk policy; never auto-accept by status alone.
7. Reject semantic fingerprint changes from overlap edits.
8. Add full-candidate fallback only for high residual blocking, no-edit Core mode and remaining token budget.
9. Run the frozen high-risk overlap holdout and compare with the archived baseline.
10. Commit the adapter without refactoring the vendor package.

### Task 9: Implement render and slice adapters

**Files:**

- Create: `src/manim_quality/rendering/interfaces.py`
- Create: `src/manim_quality/rendering/manim_adapter.py`
- Create: `src/manim_quality/rendering/slices.py`
- Test: `tests/integration/test_targeted_render.py`

**Steps:**

1. Write a fake renderer contract test.
2. Implement compile and Scene-level render.
3. Reuse unchanged slice hashes and files.
4. Re-concatenate only after accepted candidate scenes render.
5. Bind final video hash to code and slice manifest.
6. Verify failed render never promotes a revision.
7. Commit render adapters separately from Agent code.

### Task 10: Implement the Quality Orchestrator and final gate

**Files:**

- Create: `src/manim_quality/orchestrator/service.py`
- Create: `src/manim_quality/orchestrator/transitions.py`
- Create: `src/manim_quality/delivery/consistency_gate.py`
- Create: `src/manim_quality/delivery/certificate.py`
- Test: `tests/e2e/test_quality_happy_path.py`
- Test: `tests/failure_injection/`

**Steps:**

1. Write failing end-to-end tests for clean, logic-repair, overlap-repair and warning paths.
2. Implement the state machine using persisted transitions.
3. Make the orchestrator the only component allowed to promote a revision.
4. Add deterministic final checks for code/render/evidence/config version consistency.
5. Add rollback to the current stage's certified checkpoint.
6. Inject SDK timeout, checker error, render error, duplicate task and stale worker failures.
7. Confirm no failure path silently becomes PASS.
8. Commit the end-to-end quality core.

### Task 11: Add API and queue workers

**Files:**

- Create: `apps/api/main.py`
- Create: `apps/api/routes/jobs.py`
- Create: `apps/api/routes/revisions.py`
- Create: `apps/worker/main.py`
- Create: `src/manim_quality/storage/queue.py`
- Test: `tests/integration/test_api_jobs.py`
- Test: `tests/integration/test_worker_idempotency.py`

**Endpoints:**

```text
POST /v1/quality/jobs
GET  /v1/quality/jobs/{job_id}
GET  /v1/quality/jobs/{job_id}/revisions
GET  /v1/quality/jobs/{job_id}/certificate
GET  /v1/quality/jobs/{job_id}/evidence
```

**Steps:**

1. Write API contract tests and idempotency tests.
2. Persist a submission before publishing queue work.
3. Use an outbox or equivalent transaction pattern.
4. Add `stage_run_id`, worker lease, heartbeat, deadline, bounded infrastructure retry and dead-letter/HOLD transitions.
5. Add tenant quotas and request size limits.
6. Add callback delivery with retry and signature verification.
7. Commit API and worker integration.

### Task 12: Add the user modification Agent

**Files:**

- Create: `src/manim_quality/modification/planner.py`
- Create: `src/manim_quality/modification/coder.py`
- Create: `src/manim_quality/modification/service.py`
- Create: `apps/api/routes/modifications.py`
- Test: `tests/e2e/test_modification_preview_publish.py`

**Endpoints:**

```text
POST /v1/quality/jobs/{job_id}/modifications
GET  /v1/quality/jobs/{job_id}/modifications/{draft_id}
POST /v1/quality/jobs/{job_id}/modifications/{draft_id}/approve
POST /v1/quality/jobs/{job_id}/modifications/{draft_id}/discard
```

**Steps:**

1. Write tests for Scene targeting and immutable draft revisions.
2. Port useful Scene-level behavior from the existing modify worker.
3. Add targeted preview render without running the full quality chain on every conversational turn.
4. Require explicit approval before publish-quality validation.
5. A preview may use targeted checks, but every approved publish candidate must re-enter the mandatory full Logic Reviewer, then overlap detection and the final consistency gate.
6. Reject silent partial application.
7. Commit modification support.

### Task 13: Add observability and commercial policy

**Files:**

- Create: `src/manim_quality/observability/metrics.py`
- Create: `src/manim_quality/observability/audit.py`
- Create: `src/manim_quality/delivery/policy.py`
- Create: `docs/commercial-quality-policy.md`
- Test: `tests/unit/test_delivery_policy.py`

**Required metrics:**

- First-pass yield.
- Final sampled good-product rate.
- Auto-delivery rate.
- Logic and overlap trigger rates.
- Repair uplift and accepted-worse rate.
- Manual/hold/regeneration rate.
- Tokens and latency per role and per job.
- Duplicate task and rollback counts.
- User modification rate after delivery.

**Steps:**

1. Write policy table tests for hard blockers and warnings.
2. Implement `ACCEPT_WITH_WARNING` only for versioned, low-risk reasons.
3. Add per-tenant token ceilings and concurrency limits.
4. Add dashboards and alert thresholds.
5. Commit policy separately from model prompts.

### Task 14: Run holdout, load and launch validation

**Files:**

- Create: `scripts/run_holdout.py`
- Create: `scripts/run_load_test.py`
- Create: `docs/launch-checklist.md`
- Output: `evals/reports/<version>/`

**Steps:**

1. Freeze train/tuning and holdout manifests.
2. Run known-good logic probes to measure over-review and over-edit.
3. Run known-bad logic holdout and report detection, repair and verifier outcomes separately.
4. Run overlap holdout and report clean/degraded/unchanged rather than one combined success number.
5. Run user modification holdout.
6. Run 100 concurrent fake-render jobs for queue/state correctness.
7. Run a smaller real-render capacity test on target Linux infrastructure.
8. Run a canary with production submissions in shadow mode.
9. Enable automatic repair only after shadow acceptance metrics are met.
10. Record launch decision and rollback version.

## 7. Commercial Acceptance Targets

These are launch targets, not current claims:

- 100% delivered jobs have final revision, logic certificate and overlap certificate.
- 0 stale-evidence or code/video mismatch deliveries.
- 0 accepted-worse overlap patches.
- 0 duplicate uploads.
- At least 85% auto-delivery after bounded repair or accepted warning.
- Less than 5% manual intervention after regeneration fallback is connected.
- Logic no-error over-edit rate below 3% on the frozen known-good set.
- Average quality-Agent usage target below 25k tokens/job, reported with triggered high-risk tails separately.
- Logic and overlap loops never exceed two attempts.
- SDK/checker/render outages remain retryable and never silently pass.

## 8. AI Workload Decomposition

Calendar estimates are intentionally excluded. One workload unit is one bounded AI implementation loop that ends with a focused test, code review and evidence update. Units describe engineering and verification effort, not elapsed time.

| Goal | Scope | Workload units | Parallelism |
| --- | --- | ---: | --- |
| G1 Foundation | Workspace, source freeze, public contracts, state transitions | 12–16 | High |
| G2 Revision Core | Immutable revisions, artifact store, semantic fingerprints | 10–14 | High after contracts |
| G3 Agent Runtime | SDK profiles, permissions, budgets, usage and audit | 10–14 | High after skeleton |
| G4 Logic Engine | Reviewer, Coder, validators, directed Verifier and evals | 24–32 | Medium; internal parts parallel |
| G5 Overlap Integration | Vendor adapter, status policy, external render/recheck | 6–10 | High |
| G6 Quality Orchestration | Persisted state machine, rollback and final gate | 14–20 | Low; integration critical path |
| G7 Platform Interfaces | FastAPI, RabbitMQ, generation contract and callbacks | 8–12 | High after contracts |
| G8 Modification Workbench | Change planner, edit Agent, preview and approval | 10–16 | Medium |
| G9 Commercial Hardening | Observability, quotas, failure injection, holdout and load tests | 14–20 | High, then one integration review |

Expected total: approximately `110–150` bounded AI implementation units.

Backend quality MVP scope is G1 through G6: approximately `76–106` units.

Full commercial workspace adds G7 through G9: approximately `32–48` additional units.

Expected new artifacts, excluding the preserved overlap vendor package:

```text
Production modules: about 45–65 files
Test and evaluation modules: about 50–80 files
Production code: about 8k–12k lines
Tests/evals/scripts: about 7k–12k lines
Database migrations: 4–7
Public API groups: 5
Persistent quality states: about 15
```

Recommended parallel AI workstreams:

```text
Stream A: contracts + revision/storage
Stream B: shared Agent Runtime
Stream C: logic Reviewer/Coder/Verifier
Stream D: overlap adapter + render adapter
Stream E: API/queue + later modification workbench
```

Mandatory sequential integration checkpoints:

```text
Checkpoint 1: contracts frozen before service integration
Checkpoint 2: Agent Runtime verified before live logic/overlap calls
Checkpoint 3: logic and overlap services verified before orchestrator acceptance
Checkpoint 4: final gate and failure injection verified before commercial policy
Checkpoint 5: holdout and shadow evidence reviewed before automatic delivery
```

The main workload is not writing source code. It is the repeated proof cycle around logic false positives/negatives, overlap degraded acceptance, revision consistency, failure recovery and real-sample holdout results.

## 9. Completion Evidence

The project is not commercially ready until all of the following exist:

- Reproducible Linux 3.11 build.
- Database migrations and idempotent queue processing.
- End-to-end clean, logic-repair, overlap-repair and modification tests.
- Failure-injection proof for SDK, checker, renderer, queue and stale revisions.
- Frozen holdout reports with good and bad samples.
- Per-stage token and latency reports.
- Signed final quality certificate linked to the delivered revision.
- Canary report and documented rollback procedure.
