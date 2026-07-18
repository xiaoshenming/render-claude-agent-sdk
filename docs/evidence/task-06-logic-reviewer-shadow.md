# Task 6 Logic Reviewer Shadow Evidence

## Scope

This evidence covers the mandatory, read-only Claude Agent SDK Logic Reviewer.
No repair was enabled. Every SDK error, schema error, citation rejection, and
known-good non-pass remained in the denominator.

Provider credentials were injected from process memory and were not written to
the repository or reports. The evaluated model was `gemini-3.5-flash-high`
through the configured Anthropic-compatible gateway and Claude Agent SDK
`0.2.116`.

## Stabilized Final Shadow

Private evidence root:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task6-stabilized-20260711-113619\final-full-30plus6
```

The final candidate wheel ran all 30 known-bad and six known-good cases with
four workers in 252 seconds. The report SHA-256 is
`8c1106eb5b298607749aae5ab8bf522dfb7eb8e2d7ad03af0713e250f2ef2eae` and
the evaluated wheel SHA-256 is
`de84c78a55d84b6a886bcb1e71711ed38a797bc12ef3e4104e6559c102391f29`.

| Metric | Result |
| --- | ---: |
| Attempted | 36 |
| Target-error true positive | 22 |
| False negative | 8 |
| True negative | 5 |
| False positive (fail-closed) | 1 |
| Final errors | 3 |
| First-attempt errors | 8 |
| Correction attempted | 7 |
| Correction recovered | 5 |
| Target-error recall | 73.33% |
| Detection precision | 81.48% |
| Known-good non-pass rate | 16.67% |
| Total tokens | 1,750,219 |
| Average tokens/case | 48,617 |
| Average SDK turns/case | 3.58 |
| Average observed model rounds/case | 2.44 |
| Average elapsed/case | 26.4 s |

Token composition was 894,654 input tokens (51.1%), 480,607 output tokens
(27.5%), and 374,958 cache-read tokens (21.4%). SDK-reported turns and
platform-observed Assistant rounds are stored separately because SDK turn
counts include internal tool and correction events.

The three final failures were one hard output-token rejection, one SDK
maximum-turn rejection, and one second invalid structured-output rejection.
There were no usage-reconciliation or turn-count inference failures. The
single-correction limit is enforced at both SDK failure-hook and PreToolUse
domain-validation boundaries; a second invalid submission fails closed.

A preceding full run of the same behavioral candidate, before the final audit
field correction, produced 23/30 target hits (76.67%), four errors, one
known-good non-pass, and 1,631,069 tokens. The 3.33 percentage-point recall
difference is retained as observed model variance rather than selecting only
the better run. Its report remains at:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task6-stabilized-20260711-113619\full-30plus6
```

Compared with v6, final target recall improved from 56.67% to 73.33%, errors
fell from 12 to three, and known-good non-pass fell from two cases to one. The
cost increased from 38,166 to 48,617 average tokens per case because valid
bounded corrections and previously rejected outputs now complete more often.
This is a reliability gain, not a token optimization.

The SDK emitted asynchronous-generator cleanup warnings after some intentional
fail-closed terminations. They occurred after case results were persisted and
did not change report counts, but remain an upstream SDK cleanup-noise risk.

## Stabilization Decision

Task 6 now has a stable fail-closed Reviewer boundary, bounded correction,
accurate turn/token audit, deterministic citation scoring, and reproducible
30+6 evidence. It is suitable as the Reviewer checkpoint for Task 7 repair and
external verification work. It is not approved for automatic delivery:
73.33% recall remains below the 95% commercial target and one of six known-good
cases was still over-reviewed. Repair and publish remain disabled until later
tasks provide external validators, directed verification, and launch holdout
evidence.

## Full v6 Shadow

Private evidence root:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task6-v6-full-shadow-20260711-104606
```

The final staged `logic-reviewer-v6` wheel ran all 30 bad and six good cases
with four workers. It completed in 229.5 seconds of wall time. The frozen report
SHA-256 is `9786e0f10e24a86b43a379f1647acb1b7116e00dfd31fd829e6442de2780531f`.
The evaluated wheel SHA-256 is
`be45cb0778cff411d819543fe5c269202e1fe74ee5c0c393d2705cd7c9ea9971`.

| Metric | Result |
| --- | ---: |
| Attempted | 36 |
| Target-error true positive | 17 |
| False negative | 13 |
| True negative | 4 |
| False positive (fail-closed) | 2 |
| Harness/SDK errors | 12 |
| Target-error recall | 56.67% |
| Detection precision | 89.47% |
| Known-good non-pass rate | 33.33% |
| Total tokens | 1,373,976 |
| Average tokens/case | 38,166 |
| Average model turns/case | 2.36 |
| Average elapsed/case | 23.8 s |

Token composition was 841,833 input tokens (61.3%), 302,308 output tokens
(22.0%), and 229,835 cache-read tokens (16.7%). Seventeen bad calls produced an
accepted issue whose exact candidate citation covered the private mutation line.
Two bad calls passed without finding the target error. Twelve total calls failed
closed. Four good calls passed, one reported an issue, and one failed in the SDK.

Target matching is deterministic and external to the Agent: an issue counts only
when its already-verified `candidate_code` citation spans the mutation line from
private ground truth. An unrelated issue no longer raises recall. No issue-type
mapping or problem-specific matcher is used.

v6 error attribution was:

| Root cause | Count |
| --- | ---: |
| SDK usage/turn protocol | 5 |
| Decision semantic binding | 3 |
| Exact citation/source binding | 2 |
| Strict schema mismatch | 2 |

Bad samples have no video rendered from the mutated candidate. Their manifest is
therefore explicitly `code_only_mutation_probe` with no source-video hash. The
original correct video is not presented as evidence for mutated code. These are
code-review probes over renderable production-style sources, not final
post-render video certification.

## Full v5 Comparison

The preceding v5 run completed 36 cases with 11 errors and 1,491,448 tokens.
Its original report used the obsolete any-issue scorer. Offline target-line
recalculation found 19 accepted target hits (63.33% recall), including one valid
bad report that discussed an unrelated issue and must not count. v6 removed the
false video binding and shipped the target-line scorer, but did not improve
reliability; prompt iteration stops here.

## Full v4 Comparison

Private evidence root:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task6-full-shadow-20260711-095011
```

The run used a unique built wheel, four workers, 30 known-bad mutations and six
known-good probes. It completed all 36 requested cases in 220.7 seconds of wall
time.

| Metric | Result |
| --- | ---: |
| Attempted | 36 |
| True positive | 17 |
| False negative | 13 |
| True negative | 5 |
| False positive | 1 |
| Harness/SDK errors | 12 |
| Fail-closed detection recall | 56.67% |
| Detection precision | 94.44% |
| Known-good non-pass rate | 16.67% |
| Total tokens | 1,201,452 |
| Average tokens/case | 33,374 |
| Average model turns/case | 2.25 |
| Average elapsed/case | 22.7 s |

Token composition was 864,041 input tokens (71.9%), 209,292 output tokens
(17.4%), and 128,119 cache-read tokens (10.7%). Input-side accounting therefore
represented 82.6% of total usage.

Among the 18 known-bad cases that completed without an infrastructure or
binding error, 17 produced an issue (94.44%). Five of six known-good probes
passed. These conditional numbers diagnose Reviewer capability; they are not
launch acceptance metrics because failed calls cannot be removed from the
commercial denominator.

Nine of the 12 failed known-bad calls had already produced a structured
`needs_repair` diagnosis before the harness rejected it. Counting those raw
diagnoses would show that the model surfaced an issue in 26 of 30 bad cases,
but this is deliberately not reported as accepted recall.

## v4 Error Attribution

| Root cause | Count | Evidence-based action |
| --- | ---: | --- |
| Strict schema mismatch | 7 | Make every issue field explicit in the prompt; keep schema strict |
| Attempted read of `case_manifest.json` | 2 | Remove file-like provenance labels from prompt evidence; do not expand permissions |
| SDK usage/turn protocol mismatch | 2 | Add protocol event evidence before changing reconciliation; retry only as infrastructure policy |
| Inexact candidate citation | 1 | Keep exact binder; allow a bounded citation-only retry later |

The schema failures crossed geometry, proof, coordinate, and relation samples.
They were not tied to one problem. Six omitted `repairable`; two also emitted an
unsupported field. The path failures were induced by exposing
`case_manifest.json` as a source label even though it was intentionally outside
the read allowlist.

## v5 Protocol Changes

`logic-reviewer-v5` made two general changes only:

1. It lists every required issue field and forbids alternate fields.
2. It exposes scene identity as `bounded_scene_identity`, not as a readable file
   name, and explicitly limits reads to candidate and render manifest paths.

No sample ID, issue type, mutation text, expected patch, or problem-specific
branch was added. A 36-case prompt audit found zero sample-ID or private-label
leaks.

The first two v5 diagnostic probes no longer reproduced the schema or denied
path failures, but ended with a gateway usage-protocol error and an exact
citation rejection caused by mojibake in the model's copied excerpt. They are
recorded at:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task6-v5-probe-20260711-095852
```

A fresh, previously unused mutation probe then completed successfully before the
full v5 run:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task6-v5-fresh-20260711-100922
```

It correctly identified that the candidate claimed a tangent was parallel to
the radius instead of perpendicular, returned exact candidate/problem evidence,
and completed as `needs_repair` in two turns, 15.3 seconds, and 30,951 tokens.

## Dataset Limits

The six good probes are render-success samples with expected solutions, not a
human-certified clean set. One v4 mutation replaces the smoke-tuned v5 case,
but available renderable packs reuse a small set of source programs. The
replacement is independent at the mutation level, not at the source-code level.
A new production-source, human-labelled holdout is mandatory in Task 14.

Issue types are currently free text. The report field is named
`exact_issue_type_match_rate` because exact equality between labels such as
`mathematical_error` and `wrong_line_relation` is not semantic correctness.
No hand-written mapping table is used.

## Historical v6 Decision

The following decision records the earlier v6 checkpoint and is superseded by
the stabilized decision above.

The Reviewer adapter, evidence binding, fail-closed semantics, frozen evaluator,
and live shadow path are implemented. The evidence supports continuing with the
Claude Agent SDK direction, but does not support enabling automatic delivery:
12 of 36 calls did not produce an acceptable certificate, two valid bad calls
missed their target mutation, and one valid good call was over-reviewed.

Prompt iteration stops at v6 because successive full runs did not materially
improve total reliability. Before launch, the platform instead needs SDK
protocol-event diagnostics, bounded structure and citation correction reported
separately from first-attempt metrics, actual mutated-candidate rendering, and a
source-independent human-labelled holdout. Logic repair remains disabled until
those gates and Task 7 verification are complete. This commit is an honest
fail-closed Reviewer/evaluation checkpoint, not Task 6 launch acceptance.
