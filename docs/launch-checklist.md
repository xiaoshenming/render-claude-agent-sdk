# Launch Checklist

Launch evidence version: `launch-v1`

Current decision: **HOLD**. Automatic repair remains disabled.

## Completed Evidence

- [x] Frozen launch manifest verifies six source/selection manifests by SHA-256.
- [x] Logic Agent SDK probe ran on five frozen known-bad and five frozen
  known-good cases using the predeclared selection rule.
- [x] Reviewer, Coder, and directed Verifier outcomes are reported separately.
- [x] Overlap regression reports clean, degraded, rejected, unsupported, and
  unchanged counts separately; accepted-worse remains zero.
- [x] Ten generic user-modification scenarios passed; the full Task 12 E2E file
  passed `16/16`.
- [x] One hundred concurrent fake queue/render jobs completed exactly once:
  `100/100`, zero dead letters, zero duplicate handler calls, `2969 ms`.
- [x] Rollback version is recorded in the generated launch report.

## Blocking Evidence

- [ ] Logic known-bad quality: detection recall was `40%`; two repair candidates
  were produced, but exact target restoration was `0`.
- [ ] Logic known-good quality: false-positive rate was `20%`, above the `<3%`
  launch target. The false-positive patch was rejected before promotion.
- [ ] Average Reviewer use was `44,365 tokens/job`, above the `25k` target.
- [ ] Overlap evidence still lacks final real-render certification and an
  independent untouched holdout.
- [ ] A smaller real-render capacity test has not run on target Linux Manim
  infrastructure.
- [ ] A production-submission canary has not run in shadow mode.
- [ ] PostgreSQL/RabbitMQ/object-storage deployment wiring and durable metric,
  audit, dashboard, and alert sinks require deployment validation.

## Reproduction

From `D:\manim_quality_platform` in PowerShell:

```powershell
$env:PYTHONPATH = "src;."
.venv\Scripts\python.exe -m scripts.run_load_test `
  --database evals\reports\launch-v1\fake-load.sqlite3 `
  --jobs 100 --workers 10 `
  --output evals\reports\launch-v1\fake-load.json

.venv\Scripts\python.exe -m scripts.run_holdout `
  --manifest evals\launch_manifest_v1.json `
  --evidence evals\launch_evidence_v1.json `
  --output evals\reports\launch-v1\launch-report.json `
  --version launch-v1 --rollback-version 5c39be3
```

Live Agent runs require provider credentials in environment variables. Secrets
must never be placed in the command, report, manifest, or Git tree.

## Enablement Rule

Do not turn on automatic logic or overlap repair merely because code tests pass.
A new version may move from HOLD only after every blocking item above has fresh,
hash-bound evidence and the commercial policy thresholds pass. Failed evidence
must be retained; it must not be replaced by repeated sampling until a favorable
run appears.

Rollback target for `launch-v1`: `5c39be3`.
