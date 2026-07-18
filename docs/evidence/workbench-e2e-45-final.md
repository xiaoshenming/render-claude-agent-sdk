# Manim Quality Workbench E2E Report

## Executive Summary

This overnight evaluation ran the independent quality workbench end to end on 45 generated Manim jobs. The jobs came from a frozen pool of 20 moderately hard or hard math topics and were executed as three rounds of 15.

The latest configuration produced 15/15 quality-pipeline releases. Twelve were strict releases and three were warning releases. Across all evolving configurations, 37/45 jobs reached a release state, including nine warning releases.

All 37 final MP4 files are silent 854x480 validation renders. This matches the experiment's "renderable is enough" scope, but they are not commercial finished videos. If commercial delivery requires TTS, audio, or audio-video synchronization, this experiment produced zero finished products; it validated the code-quality workbench only.

The strongest verified conclusion is that the generation, render, mandatory Logic Reviewer, real layout probe, conditional overlap Agent, checker recheck, and final re-render can operate as one bounded pipeline. The overlap repair direction is validated. The generated batch did not trigger Logic Coder, so this experiment does not prove logic-repair success.

## Scope and Configuration

- Worktree: `D:\codex-worktrees\manim_quality_platform\workbench-e2e-45`
- Branch: `codex/workbench-e2e-45`
- Hardened code commit: `37e2657`
- Run root: `D:\manim_quality_platform_runs_20260712\workbench_e2e_45`
- Generation gateway: Anthropic-compatible `/v1/messages`
- Generation and Agent model: `gemini-3.5-flash-high`
- Claude Agent SDK: `0.2.116`
- Generation prompts: existing prompt IDs 95, 98, and 99 from the upstream SQLite database
- Render runtime: local Manim 0.19, low-quality deterministic validation render
- Logic input: digest v2.1; the new expected/actual relation probe was intentionally not integrated
- Overlap tools: real DEV-PB5 layout probe plus the materialized `quality_repair` Claude SDK package
- Agent tool surface: existing constrained Read/Edit profiles; no Bash was added

The API key was supplied only through process environment. A post-run scan found no `sk-...` secret patterns in source or run artifacts.

## Pipeline

1. Render a prompt from the existing upstream prompt database.
2. Generate a complete `candidate.py`.
3. Render the baseline video.
4. If baseline render fails in Round 3, perform one bounded full regeneration with a 2,000-character error tail.
5. Run the mandatory Logic Reviewer.
6. Hold `human_review` and Reviewer errors; allow `pass` and non-blocking `record_only`.
7. Run the real layout probe.
8. Invoke the overlap Agent only when blocking layout evidence exists.
9. Re-run the checker; accepted changed candidates must re-render.
10. Persist a final status, source, video, token usage, timing, Agent evidence, and logs.

## Frozen Workload

The pool contains 20 fixed tasks:

- 12 geometry and proof tasks
- 4 function and coordinate-geometry tasks
- 2 algebra tasks
- 1 probability task
- 1 statistics task

The 45 slots rotate deterministically through this pool. Each adjacent pair of rounds shares 10 repeated topics. This is more informative than unrelated batches, but it is not a perfect same-sample A/B test because five topics differ between adjacent rounds and every generation is stochastic.

## Round Results

| Round | Version | Quality release | Strict | Warning | Held | Tokens | Avg tokens | Avg job time |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | `74c8f17` | 10/15 (66.7%) | 8 | 2 | 5 | 706,310 | 47,087 | 69.4 s |
| 2 | `96278bf` | 12/15 (80.0%) | 8 | 4 | 3 | 792,361 | 52,824 | 119.3 s |
| 3 | `0d3ca7d` | 15/15 (100%) | 12 | 3 | 0 | 863,293 | 57,553 | 94.1 s |
| Total | evolving | 37/45 (82.2%) | 28 | 9 | 8 | 2,361,964 | 52,488 | 94.3 s |

On the 10 repeated topics between consecutive rounds:

- Round 1 to Round 2: 6/10 to 8/10 deliverable.
- Round 2 to Round 3: 7/10 to 10/10 deliverable.

This supports improvement, but it does not isolate every change from generation randomness.

## Iterations

### Round 1 baseline

Round 1 exposed four generic problems:

- no retry for an HTTP 502;
- generated Pango style-key conflicts;
- invalid LaTeX;
- incorrect routing of non-blocking `record_only`;
- platform semantic fingerprint rejecting vendor-clean layout candidates.

### Round 2

Round 2 added:

- one retry for transient or incomplete generation;
- generic Pango and LaTeX prompt constraints;
- correct `record_only` routing;
- vendor-clean adoption only after compile, checker recheck, diff audit, and external render, while retaining a warning.

Delivery increased from 10/15 to 12/15. One transient generation request recovered on its second request.

### Round 3

Round 3 added only:

- one non-Agent full-regeneration recovery after baseline render failure;
- stronger universal rules that prohibit Chinese inside Tex/MathTex and prohibit overlapping Pango mapping keys even when styles are identical.

Three jobs used render recovery and all three delivered. Round 3 finished 15/15.

## Agent Metrics

### Generation

- Reported tokens: 1,067,367
- Average per scheduled job: 23,719
- Round 2 network retries that recovered: 1
- Round 3 render-regeneration recoveries: 3/3 successful

### Logic Reviewer

- Jobs attempted: 39
- Reported tokens: 787,252
- Average per attempted job: 20,186
- Average turns: 2.85
- Average observed model rounds: 1.87
- Decisions in completed reviews: 38 `pass`, 1 `record_only`
- Provider failures: 1 `server_error`, held fail-closed
- Logic Coder repairs: 0

The absence of `needs_repair` means this batch validates mandatory logic review and routing, not logic repair quality.

### Layout and Overlap

- Layout checks after successful logic stage: 37
- Jobs with positive blocking evidence: 12
- Agent rounds: 12 total, exactly one per triggered job
- Average triggered-job layout tokens: 42,279
- Average triggered-job layout-stage time: 93.7 s
- Aggregate blocking count: 36 before, 6 after
- Accepted changed candidates: 7
- Unresolved warning releases retaining the original video: 5

Four experimental candidates were vendor-clean but retained a platform semantic-fingerprint warning. They passed vendor compile, checker recheck, diff audit, and final Manim re-render, and their issue-time frames were visually checked. Independent review correctly noted that this is not a mathematical semantic re-verification, so the hardened harness now disables this fallback by default.

## Validation

- All 45 slots have terminal `job_summary.json` records.
- All 37 released jobs have a persisted silent `video_final.mp4`.
- ffprobe successfully read 37/37 final videos.
- All 37 videos are H.264, 854x480, 44.47-76.60 seconds, with no audio stream.
- Final deliverable videos total 34,172,401 bytes.
- Seven accepted overlap repairs have before/after frame pairs.
- All seven frame pairs were visually inspected at detector-recommended timestamps; labels or content moved away from conflicts without changing the shown mathematical answer.
- The final E2E unit and engineering suite passed: 28 tests.
- The expanded Logic/Overlap regression scope passed: 260 tests.
- The full repository suite reported 1,356 passed, 2 failed, and 4 platform skips. The two failures are the pre-existing frozen holdout/source-provenance hash mismatches; no frozen hashes were rewritten.
- Ruff passed on all new E2E modules.
- New Python modules remain below 300 lines; the largest is 253 lines.
- Secret scan found zero key-like values in source and run artifacts.
- The expected/actual relation probe has zero imports in this E2E harness.

+## Post-Run Harness Hardening

An independent code review was performed after the 45-job run. The following fixes are now in the branch but were not used to recalculate the frozen three-round metrics:

- Manim and layout-probe subprocess environments remove API keys, auth tokens, passwords, and secret-like variables before generated code executes.
- A nonzero layout-probe exit always overrides stale `ok=true` JSON.
- Every unhandled per-job exception becomes an atomic terminal record instead of stopping the batch.
- `job_summary.json` writes are atomic, preventing concurrent report reads from seeing half-written JSON.
- Provider usage from a successful HTTP response is accumulated even when its generated code is rejected and retried.
- `record_only` may release only through a low-risk warning policy: non-blocking, no human-review requirement, and every issue severity must be low.
- Recovering a vendor candidate rejected by the platform semantic fingerprint is disabled by default. Production use now retains the original code unless an explicit semantic re-verification path is added.
- Headline reporting separates strict delivery, warning release, and combined quality-release counts.

The original 45 runs executed before subprocess environment sanitization. A full artifact scan found no secret-like value, but this proves only that these runs did not leak; the current code fixes the unsafe boundary.


## Warning Policy

A warning release is not equal to a strict pass.

The nine warning releases contain:

- four vendor-clean, externally re-rendered candidates where the platform semantic fingerprint remained conservative;
- five jobs where overlap repair did not produce an adoptable candidate within the single-round budget, so the original renderable video was retained with evidence.

Commercial delivery should distinguish these states in the final score. If only strict results are customer-visible, the strict quality-gate yield is 28/45 (62.2%), and the latest-round strict yield is 12/15 (80%). These are still silent validation outputs, not finished customer videos.

## What This Proves

- The independent workbench can consume an external generation interface.
- Mandatory Logic Reviewer execution is practical at about three turns.
- Real overlap detection and conditional Claude SDK repair work on newly generated code.
- A one-round overlap Agent can produce accepted, re-renderable fixes.
- Bounded full regeneration can recover common baseline render errors without introducing another general-purpose Agent.
- Complete evidence, videos, diffs, tokens, timing, and statuses can be persisted for batch production.

## What This Does Not Prove

- It does not prove that mathematical logic errors are repaired, because Logic Coder was never triggered.
- It does not prove all 37 delivered videos are pedagogically perfect; ffprobe and sampled frame review are not full human viewing.
- It does not establish an unbiased 100% production yield; Round 3 is one 15-job cohort, includes warning releases, and has no audio.
- The reported token units combine provider-reported input, output, and, for Agent stages, cache accounting. They should not be treated as exact billing tokens without provider-specific pricing reconciliation.

## Recommended Next Work

1. Freeze the current Round 3 harness. Do not add more prompt rules from these 20 tasks.
2. Build a separate blinded logic-repair benchmark with real known-bad generated videos and independent expected answers. Require actual `needs_repair -> patch -> validator -> re-render` evidence.
3. Add one provider-level retry for transient Logic Reviewer `server_error`; do not retry semantic `human_review`.
4. Calibrate the final commercial score so unresolved overlap warnings are not counted as strict good products.
5. Review the seven accepted overlap diffs and the five unresolved warning videos with the product team before changing the semantic fingerprint policy.
6. Connect the external generation API through the existing submission contract only after these evidence fields are preserved in the production storage layer.

## Artifact Index

- Complete JSON report: `D:\manim_quality_platform_runs_20260712\workbench_e2e_45\report.json`
- Flat CSV: `D:\manim_quality_platform_runs_20260712\workbench_e2e_45\report.csv`
- Before/after video HTML: `D:\manim_quality_platform_runs_20260712\workbench_e2e_45\before_after.html`
- Visual repair pairs: `D:\manim_quality_platform_runs_20260712\workbench_e2e_45\report_assets`
- Round stdout/stderr: `round1_*.log`, `round2_*.log`, `round3_*.log`
- Invalid smoke evidence: `smoke_invalid_contract`
- Probe-environment smoke evidence: `smoke_probe_env_fixed`
- Implementation plan: `docs/plans/2026-07-12-workbench-e2e-45.md`
- Round reports: `docs/experiments/workbench-e2e-round-1.md`, `workbench-e2e-round-2.md`
