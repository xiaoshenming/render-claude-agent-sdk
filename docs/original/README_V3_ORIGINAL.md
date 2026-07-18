# Manim Quality Platform

Independent quality-control workspace for AI-generated Manim code.

Current status: Tasks 1-5 are complete. The production Logic Reviewer and its
frozen shadow-evaluation harness are under Task 6 validation; logic repair,
overlap integration, orchestration, and delivery remain disabled.

Read `AGENTS.md` before changing any file.

## Intended Flow

```text
submission -> baseline render -> mandatory logic review
           -> conditional logic repair and verification
           -> mandatory overlap detection
           -> conditional overlap repair and external recheck
           -> deterministic consistency gate -> publish once
```

## Local Checks

```powershell
python -m pytest -q
python scripts/check_engineering_standards.py
```

Logic shadow evaluation uses an isolated, non-editable project install so the
wheel-packaged frozen logic engine is exercised instead of pytest-only import
paths. See `evals/README.md`.
