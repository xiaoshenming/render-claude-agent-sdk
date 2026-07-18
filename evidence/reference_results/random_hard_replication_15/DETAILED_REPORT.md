# Random Hard Replication: 15-Task Report

Run date: 2026-07-13

## Conclusion

This was a fresh-code replication over 15 randomly selected `hard` tasks. The
selection was sampled without replacement from the 17 hard tasks in the frozen
workload using seed `202607130826`.

- Strict release: 6/15 (40.0%).
- Warning release: 9/15 (60.0%).
- Runtime quality release: 15/15, but this is not the strict success rate.
- Baseline render: 15/15 on the first generation attempt.
- Logic Reviewer: 15 pass, 0 repair, 0 hold, 0 tool errors.
- Blocking overlap detected: 9/15.
- Overlap repair adopted: 0/9.
- Final videos readable: 15/15, H.264 854x480, 44.93-79.00 seconds.
- Audio tracks: 0/15.

The batch confirms that the present bottleneck is overlap repair acceptance.
Generation, rendering, and mandatory logic review were stable. Reporting all
15 as a quality success would be misleading because nine retained the original
candidate with an overlap warning.

## Per-task results

| Slot | Task | Result | Logic | Layout | Tokens |
| --- | --- | --- | --- | --- | ---: |
| random-hard-001 | prob-001 | warning | pass | 1->0, rejected | 62,653 |
| random-hard-002 | geo-009 | warning | pass | 1->0, rejected | 110,731 |
| random-hard-003 | fun-001 | warning | pass | 4->0, rejected | 101,033 |
| random-hard-004 | geo-001 | warning | pass | 20->16, round cap | 111,056 |
| random-hard-005 | geo-003 | strict | pass | clean | 40,468 |
| random-hard-006 | geo-005 | warning | pass | 4->0, rejected | 72,772 |
| random-hard-007 | geo-011 | strict | pass | clean | 30,994 |
| random-hard-008 | fun-002 | warning | pass | 9->5, budget error | 111,865 |
| random-hard-009 | geo-007 | strict | pass | clean | 60,181 |
| random-hard-010 | fun-003 | warning | pass | 4->1, round cap | 84,280 |
| random-hard-011 | geo-002 | strict | pass | clean | 44,285 |
| random-hard-012 | geo-008 | warning | pass | 1->0, rejected | 84,244 |
| random-hard-013 | alg-001 | strict | pass | clean | 35,331 |
| random-hard-014 | geo-012 | warning | pass | 11->0, budget error | 143,818 |
| random-hard-015 | fun-004 | strict | pass | clean | 35,832 |

The process ran from 08:28:20 to 08:37:09, about 8 minutes 49 seconds with
three concurrent jobs. Sum of per-job elapsed time was about 24 minutes because
the jobs overlapped.

## Token profile

Total recorded tokens: 1,129,543. Average: 75,302.87 per task.

| Stage | Tokens | Share |
| --- | ---: | ---: |
| Generation | 362,818 | 32.1% |
| Logic review | 320,403 | 28.4% |
| Logic repair | 0 | 0.0% |
| Overlap repair | 446,322 | 39.5% |

Generation used 63,664 input and 299,154 output tokens. Logic review used
208,292 input, 78,940 output, and 33,171 cache-read tokens over 15 calls, with
2.93 SDK turns per call. The nine overlap calls used 337,115 input and 109,207
output tokens; they separately reported 236,246 cache-read tokens.

## Overlap diagnosis

Six Agent candidates reached zero blocking:

- `random-hard-001`: widened a summary box and reduced summary font size.
- `random-hard-002`: translated the right-side explanation column.
- `random-hard-003`: moved line and point labels.
- `random-hard-006`: translated the entire geometry left without changing
  relative coordinates.
- `random-hard-012`: moved the dynamic P label diagonally away from the point.
- `random-hard-014`: translated geometry and explanation blocks, and changed
  grouped FadeOut calls into equivalent individual FadeOut calls.

The first five were rejected by the semantic fingerprint even though their core
diffs are predominantly layout-only. `random-hard-014` exceeded the 60k budget
inside one vendor call, despite eventually reporting 11->0. These candidates
were not adopted, so the official videos remain warning releases.

Three candidates did not reach zero:

- `random-hard-004`: 20->16. Translating the whole diagram could not solve a
  large number of internal collisions.
- `random-hard-008`: 9->5, then exceeded budget.
- `random-hard-010`: 4->1 and hit the one-round cap.

This separates two problems that need different treatment:

1. Safe-looking label/column/rigid-translation patches are being rejected by a
   coarse semantic fingerprint.
2. High-overlap global layouts are not repairable by one local Agent round and
   should usually be regenerated from a better layout plan.

## Comparison with the preceding 15-task batch

| Metric | Previous batch | Random hard batch |
| --- | ---: | ---: |
| Strict release | 7/15 | 6/15 |
| Warning release | 7/15 | 9/15 |
| Hold | 1/15 raw | 0/15 |
| Logic repairs adopted | 1 | 0 |
| Overlap repairs adopted | 2 | 0 |
| Total tokens | 1,113,724 | 1,129,543 |
| Average tokens | 74,248 | 75,303 |

Token cost is reproducibly around 74k-75k per task. Strict quality did not
improve with more samples. The additional run therefore adds enough evidence to
stop blind scaling and work on the overlap decision layer.

## Recommended next action

Do not start another large batch with the same configuration. Build and test a
general typed patch gate on held-out cases:

- Automatically recognize invariant rigid translations, label direction/buff,
  and font-size/container changes as layout candidates.
- Require zero blocking, successful rerender, unchanged mathematical claims,
  and a bounded visual-regression check before adoption.
- Continue rejecting formula/text edits, object deletion, constructor changes,
  and animation rewrites unless they pass stronger review.
- Route high-overlap cases, for example more than 5 blocking issues or poor
  first-round reduction, to one layout-aware regeneration instead of repeatedly
  spending overlap Agent tokens.
- Preserve strict, warning, and hold metrics separately.

No task-specific conditions or knowledge-point names should enter this gate.

## Artifacts

- Frozen selection: `selection_manifest.json`
- Machine report: `report.json`
- Flat report: `report.csv`
- Video comparison page: `before_after.html`
- Process output: `run_stdout.log`, `run_stderr.log`
- Per-task generation, SDK, repair, detector, diff, and render evidence:
  `round-4/<slot>/`

The initial terminal line `jobs=0` in `run_stdout.log` came from the report
builder previously requiring task directories to start with `slot-`. All 15 job
summaries were present. The report discovery rule was generalized and the root
reports above were rebuilt without rerunning any model call.
