# Geometry Inspector MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a versioned, facts-only Geometry Inspector that lets the mandatory Logic Reviewer verify fatal visual-semantic geometry contradictions without sample-specific rules or unrestricted execution.

**Architecture:** The quality platform consumes an immutable `geometry-snapshot.v1` artifact supplied by a render adapter and evaluates a small whitelist of geometric relations locally. A single in-process Claude Agent SDK MCP tool exposes bounded queries over that artifact; it never returns repairs or a delivery decision. A static AST index supports local MVP evaluation and returns `unknown` whenever runtime state cannot be proven.

**Tech Stack:** Python 3.11, dataclasses, `ast`, exact rational arithmetic where possible, Claude Agent SDK 0.2.115 in-process MCP, pytest, Ruff.

---

## Non-Negotiable Boundaries

- No sample IDs, expected mutations, known coordinates, repair values, or server error descriptions in production code or prompts.
- Private server annotations are evaluation truth only and never enter Reviewer input.
- No Bash, Python REPL, `eval`, arbitrary import, arbitrary file path, network MCP, or candidate-code execution.
- The tool returns only `known/unknown`, relation truth, observed measurements, assumptions, bounded source evidence, engine version, and input hashes.
- `unknown` cannot support PASS or automatic repair.
- The Geometry Inspector cannot certify its own repair; the outer harness must recompute frozen predicates after re-render.
- Existing `evidence-v1`, `digest-v2`, and `digest-v2-1` remain rollback-safe.
- Do not modify frozen vendor packages.

## MVP Scope

Supported object facts:

- point position;
- line start/end and optional endpoint references;
- circle center/radius;
- polygon vertices;
- source Scene and line binding.

Supported relations:

- `line_endpoints`;
- `point_on_line`;
- `point_on_circle`;
- `parallel`;
- `perpendicular`;
- `collinear`;
- `equal_length`;
- `midpoint`.

Deferred: label proximity, angle/arc binding, Updaters, arbitrary custom Mobjects, 3D projection, visual occlusion, and full timeline capture.

### Task 1: Freeze Snapshot And Fact Contracts

**Files:**
- Create: `src/manim_quality/geometry/schemas.py`
- Create: `src/manim_quality/geometry/__init__.py`
- Test: `tests/unit/geometry/test_schemas.py`

**Steps:**

1. Write failing tests for a valid snapshot, code-hash binding, immutable objects, bounded source lines, and `known/unknown` result invariants.
2. Run `D:\manim_quality_platform\.venv\Scripts\python.exe -m pytest tests/unit/geometry/test_schemas.py -q` and confirm RED because the module does not exist.
3. Implement small frozen dataclasses and strict parsers for `geometry-snapshot.v1` and `geometry-fact.v1`.
4. Reject unknown fields, repair-oriented keys, NaN/infinity, empty IDs, duplicate IDs, invalid line ranges, and unbounded excerpts.
5. Run focused tests and Ruff; commit `feat: add geometry snapshot contracts`.

### Task 2: Implement Exact Relation Kernel

**Files:**
- Create: `src/manim_quality/geometry/relations.py`
- Create: `src/manim_quality/geometry/numeric.py`
- Test: `tests/unit/geometry/test_relations.py`

**Steps:**

1. Write failing table tests for true, false, degenerate, near-boundary, unsupported, and missing-entity cases.
2. Verify RED before production code.
3. Implement exact integer/fraction operations when inputs permit; use explicit bounded tolerance only for floating observations.
4. Return `unknown` for zero-length lines, ambiguous dimensions, dynamic values, unsupported relations, and tolerance-boundary cases.
5. Add property tests with deterministic random seeds for symmetry and translation/rotation invariants.
6. Run focused tests and Ruff; commit `feat: add geometry relation kernel`.

### Task 3: Build Static Candidate Geometry Index

**Files:**
- Create: `src/manim_quality/geometry/static_index.py`
- Create: `src/manim_quality/geometry/source_binding.py`
- Test: `tests/unit/geometry/test_static_index.py`

**Steps:**

1. Write failing tests for numeric point assignments, `Line`, `DashedLine`, `Dot`, `Circle`, and `Polygon` constructor binding.
2. Add negative tests for Updaters, loops, unknown helpers, post-construction transforms, and nonliteral expressions; all must become `unknown`, never guessed.
3. Verify RED.
4. Implement AST-only indexing with stable object IDs based on Scene, assigned name, source line, and constructor type.
5. Include a provenance flag `static_initial_state`; never label it runtime-final geometry.
6. Run focused tests and Ruff; commit `feat: index static geometry evidence`.

### Task 4: Define Renderer Snapshot Adapter Boundary

**Files:**
- Create: `src/manim_quality/geometry/capture_adapter.py`
- Create: `docs/contracts/geometry-snapshot-v1.md`
- Test: `tests/unit/geometry/test_capture_adapter.py`

**Steps:**

1. Write failing tests for converting duck-typed renderer observations into the snapshot contract without importing Manim.
2. Verify RED.
3. Implement adapter inputs for points, lines, circles, and polygons plus checkpoint metadata.
4. Require caller-supplied stable object/source identity; reject anonymous runtime objects instead of inventing names.
5. Document how a future render worker supplies post-`play` or final-visible checkpoints.
6. Run focused tests and Ruff; commit `feat: define geometry capture adapter`.

### Task 5: Add Read-Only SDK Tool Infrastructure

**Files:**
- Create: `src/manim_quality/agents/read_tools.py`
- Modify: `src/manim_quality/agents/profile.py`
- Modify: `src/manim_quality/agents/guards.py`
- Modify: `src/manim_quality/agents/_runtime_models.py`
- Modify: `src/manim_quality/agents/_backend_request.py`
- Modify: `src/manim_quality/agents/claude_sdk.py`
- Modify: `src/manim_quality/agents/_controls.py`
- Test: `tests/unit/agents/test_read_tools.py`
- Test: `tests/unit/agents/test_guards.py`
- Test: `tests/unit/agents/test_claude_sdk.py`

**Steps:**

1. Write failing tests for immutable tool grants, unknown-tool denial, per-tool call limits, result-size limits, timeout behavior, and audit hashes.
2. Add a real SDK integration test that discovers and freezes the observed MCP tool name through `PreToolUse`.
3. Verify RED.
4. Add a registry of explicitly granted read-only providers; keep built-in Reviewer tools constrained independently.
5. Bind only the requested in-process SDK MCP server with `strict_mcp_config=True`.
6. Ensure every custom call traverses `PreToolUse -> RuntimeControls -> ToolGuard -> BudgetTracker`.
7. Record normalized input plus bounded result hash/status, not full private evidence or absolute paths.
8. Run all agent tests and Ruff; commit `feat: support bounded readonly sdk tools`.

### Task 6: Expose One Geometry Inspector Tool

**Files:**
- Create: `src/manim_quality/geometry/sdk_tool.py`
- Create: `src/manim_quality/geometry/service.py`
- Test: `tests/unit/geometry/test_sdk_tool.py`

**Steps:**

1. Write failing tests for the single `inspect_geometry_relation` schema and each allowed relation.
2. Verify RED.
3. Accept only logical object IDs from the bound snapshot; reject paths, code strings, expressions, extra fields, and more than four operands.
4. Return at most 2,000 characters with `known/unknown`, truth, observations, assumptions, source bindings, snapshot hash, and code hash.
5. Hard-limit to two geometry calls per Reviewer run and 200 ms per calculation.
6. Run focused and agent integration tests; commit `feat: add geometry inspector sdk tool`.

### Task 7: Add Shadow-Only Reviewer Version

**Files:**
- Create: `src/manim_quality/logic/prompts/reviewer_geometry_v1.md`
- Modify: `src/manim_quality/logic/review_input.py`
- Modify: `src/manim_quality/logic/reviewer.py`
- Modify: `evals/_logic_shadow_case.py`
- Modify: `evals/run_logic_reviewer_shadow.py`
- Test: `tests/unit/logic/test_review_input_versions.py`
- Test: `tests/unit/logic/test_reviewer.py`
- Test: `tests/unit/logic/test_eval_runtime_policy.py`

**Steps:**

1. Write failing tests for explicit `digest-v2-2-geometry` and `logic-reviewer-v8-geometry` versions.
2. Require at most two geometry calls, at most one bounded `Read` with `offset/limit`, then one structured submission.
3. Keep geometry facts separate from semantic decisions: only the Agent may bind a contradicted relation to a problem/answer claim.
4. Derive redundant protocol flags in the harness where possible instead of asking the model to coordinate them.
5. Keep production default unchanged; commit `feat: add geometry reviewer shadow route`.

### Task 8: Freeze Tool-Level Evaluation Pack

**Files:**
- Create: `evals/geometry_inspector_v1/selection.json`
- Create: `evals/geometry_inspector_v1/README.md`
- Create: `evals/run_geometry_inspector_eval.py`
- Test: `tests/unit/geometry/test_eval_manifest.py`

**Steps:**

1. Select the 11 server-derived production geometry contradictions from `prod_hard_logic_fixable_50_v1` and at least 11 correct controls.
2. Store only IDs, artifact paths, hashes, relation labels, and private truth outside Agent input.
3. Add contamination tests proving server descriptions, repair policies, expected coordinates, and move-point hints never enter snapshots or prompts.
4. Evaluate deterministic support coverage, known-result accuracy, unknown rate, latency, and reproducibility before any model call.
5. Require zero wrong `known` results; unsupported cases may be `unknown`.
6. Commit `test: freeze geometry inspector evaluation pack`.

### Task 9: Run Live Shadow A/B And Decide

**Files:**
- Create: `docs/experiments/geometry-inspector-v1-results.md`
- Generated ignored evidence: `evals/reports/geometry-inspector-v1/`

**Steps:**

1. Run baseline `digest-v2-1` and experimental geometry route on the same frozen selection, model, provider, concurrency, and budgets.
2. Measure target recall, known-good false positives, structured failures, full-file Reads, tool calls, total/input/output/cache tokens, turns, latency, and unknown routing.
3. Inspect every changed decision against private truth; do not accept aggregate numbers alone.
4. Do not connect automatic repair unless all gates pass:
   - zero wrong deterministic `known` results;
   - geometry-subset recall improves by at least 15 percentage points;
   - known-good false-positive rate below 10%;
   - structured-output failures zero;
   - average tokens no higher than 25,000;
   - average model rounds no higher than 2.2;
   - no sample-specific production logic.
5. Record evidence hashes and a promote/iterate/reject decision; commit the report.

## Verification Commands

Run after each task and again before completion:

```powershell
D:\manim_quality_platform\.venv\Scripts\python.exe -m pytest -q
D:\manim_quality_platform\.venv\Scripts\python.exe -m ruff check .
git diff --check
```

The full suite baseline is `1211 passed, 4 skipped`; skips are Windows symlink privilege checks only.
