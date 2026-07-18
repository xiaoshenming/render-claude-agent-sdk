# Workbench Holdout 20 Validation Report

Date: 2026-07-13

## Scope

- 20 new medium-hard or hard math tasks
- Fresh stochastic Manim generation
- Baseline render
- Mandatory Logic Reviewer
- Conditional Logic Coder
- Layout detection and conditional overlap Agent
- Final render and artifact persistence
- Independent code, claim, geometry, and critical-frame audit

The workload does not reuse the 10 mutation cases from the preceding logic-repair
benchmark. The current Harness and Agent prompts were frozen before this run.

## Pipeline Results

| Metric | Result |
|---|---:|
| Scheduled jobs | 20 |
| Baseline renderable | 20/20 |
| First-pass strict delivery | 10/20 |
| First-pass warning release | 9/20 |
| First-pass logic hold | 1/20 |
| Bounded logic retry recovered | 1/1 |
| Final readable videos | 20/20 |
| Strict autonomous results after retry | 11/20 |
| Visually acceptable after evidence review | about 13/20 |
| Logic Coder triggered | 0 |

The visually acceptable count adds two obvious detector false positives to the
strict count. It does not promote the six real clipping/overlap warnings or the
one minor warning to strict delivery.

## Logic Audit

- First Reviewer pass: 19/20.
- One Reviewer call failed closed because the model attempted to read a
  non-existent `helper/candidate.py` path.
- One bounded retry used the same candidate and evidence; it returned `pass`.
- Independent extraction of visible mathematical claims matched the frozen
  expected solutions for all 20 tasks.
- Static geometry and critical-frame review found no point, line, curve, or
  theorem relation contradicting the expected solution.
- No generated candidate received `needs_repair`, so Logic Coder was not invoked.

This run validates natural-generation logic quality and mandatory review, but it
does not add new evidence about Logic Coder repair recall. The separate mutation
benchmark remains the evidence for logic repair.

## Layout Audit

- Initial layout-clean jobs after the recovered case: 9.
- Jobs that triggered overlap repair: 11.
- Strictly accepted repaired candidates: 2.
- Warning releases retaining the original candidate: 9.

Warning classification:

| Class | Count | Slots |
|---|---:|---|
| Real clipping or overlap | 6 | 002, 003, 005, 011, 012, 015 |
| Detector false positive | 2 | 009, 016 |
| Minor visual contact | 1 | 010 |

Five rejected repair candidates reached zero blocking findings but were stopped
by the semantic fingerprint guard. Three repairs exceeded the 60k remaining-token
budget. One made no progress. These are Harness/overlap-stage optimization targets,
not logic failures.

## Per-Case Audit

| Slot | Topic | Pipeline | Logic | Visual audit |
|---|---|---|---|---|
| 001 | Angle bisector theorem | strict | pass | clean |
| 002 | Parabola tangent | warning | pass | real transient text overlap |
| 003 | Circle chord | warning | pass | formula overflow and label contact |
| 004 | Quadratic parameter roots | strict | pass | clean |
| 005 | Median and Heron area | warning | pass | multiple formulas clipped right |
| 006 | Bayes probability | strict | pass | clean |
| 007 | Rational function | strict | pass | clean |
| 008 | Trapezoid diagonals | strict repaired | pass | clean after accepted repair |
| 009 | Absolute-value equation | warning | pass | detector counted axis tick labels |
| 010 | Right-triangle incircle | warning | pass | minor title/label contact |
| 011 | Piecewise continuity | warning | pass | formulas clipped outside frame |
| 012 | Coordinate orthocenter | warning | pass | geometry line crosses text region |
| 013 | Recurrence sequence | strict | pass | clean |
| 014 | Parallelogram coordinates | strict | pass | clean |
| 015 | Sine transformation | warning | pass | amplitude formula clipped right |
| 016 | AM-GM minimum | warning | pass | detector counted axis tick labels |
| 017 | Intersecting chords | strict | pass | clean |
| 018 | Mean and variance | recovered strict | retry pass | clean |
| 019 | Hypergeometric distribution | strict repaired | pass | clean after accepted repair |
| 020 | Cyclic rectangle | strict | pass | clean |

## Cost and Throughput

| Stage | Tokens |
|---|---:|
| Generation | 510,743 |
| Logic Reviewer, first pass | 372,992 |
| Logic Reviewer retry | 17,190 |
| Logic Coder | 0 |
| Layout stage | 546,477 |
| Total including retry | 1,447,402 |
| Average including retry | 72,370/job |

- Wall-clock batch time: 840.8 seconds with three workers.
- Average summed per-job elapsed time: 122.9 seconds.
- Video duration range: 44.87 to 71.80 seconds.
- Generation retries: 3.

Layout is the largest token consumer and the main source of non-strict output.

## Evidence

- `report.json`: original first-pass machine report
- `report.csv`: flat first-pass status report
- `stage_summary.csv`: stage-level status and token summary
- `before_after.html`: playable baseline/final video comparison
- `qa_contact_70pct.png`: 20-video 70 percent contact sheet
- `qa_warning_contact.png`: detector-recommended warning frames
- `round-1/slot-018/recovery_summary.json`: bounded recovery evidence
- `round-1/slot-018/video_final_recovered.mp4`: recovered final video

## Conclusion

The end-to-end architecture runs reliably enough to produce 20/20 readable
videos after one bounded infrastructure retry, and this cohort showed strong
natural mathematical correctness. The commercial bottleneck is now layout
acceptance rather than logic repair. Under autonomous strict delivery the yield
is 55 percent; after evidence-backed removal of two detector false positives it
is approximately 65 percent. Warning releases must remain below strict customer
delivery until clipping and semantic recheck are improved.
