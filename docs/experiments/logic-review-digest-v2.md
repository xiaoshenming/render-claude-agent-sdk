# Logic Review Digest V2 Experiment

## Scope

Digest v2 tests whether a facts-only mathematical index can improve Logic
Reviewer detection quality and reduce tokens without changing repair behavior.
It is opt-in and does not replace the production default.

## Version Matrix

| Route | Input version | Prompt version | Status |
| --- | --- | --- | --- |
| Baseline | `evidence-v1` | `logic-reviewer-v6` | default, rollback |
| Experiment | `digest-v2` | `logic-reviewer-v7-digest` | shadow only |

Every Agent call persists its prompt version. Every shadow report persists the
review input version. The experiment cannot silently change the baseline route.

## Frozen Diagnostic Selection

- Selection: `evals/logic_digest_ab_v1/selection.json`
- SHA-256:
  `25c3e62ad4bbd059d526ed8e862f20ab7684475c1a512082f8ae7cae42d57fad`
- Composition: 10 known-bad mutations and 6 known-good controls.
- Corpus role: diagnostic regression, not locked holdout.

The first ten launch-v1 cases already have baseline output. Only the six missing
baseline cases need a new v1 call before the 16-case v2 run.

## Digest Contract

Digest v2 includes:

- problem, planning, and expected-answer provenance;
- Scene names and source line bounds;
- visible mathematical claims;
- existing deterministic logic facts;
- numeric vector assignments such as point coordinates;
- bounded Line, Circle, Angle, label, text, and formula construction arguments;
- explicit facts-not-fixes input policy.

It excludes full Scene excerpts, helper excerpts, external diagnoses, repair
hints, expected mutation types, sample IDs, and reference patches. The complete
candidate remains read-only and available on demand.

## Local Size Audit

Across the frozen 16-case selection:

| Metric | Evidence v1 | Digest v2 |
| --- | ---: | ---: |
| Average JSON characters | 15,751 | 9,604 |
| Relative reduction | - | 39.0% |

Digest v2 retained 19-81 construction facts and 0-6 numeric vectors per case.
This proves only payload reduction, not detection improvement.

## Decision Gates

Do not connect Digest v2 to automatic repair unless the live A/B shows:

- materially higher known-bad detection;
- lower or non-worse known-good false positives;
- lower average tokens and no harmful tail increase;
- no sample-specific logic in production code;
- stable structured-output and tool behavior.

The first technical target is at least 70% detection recall, below 10% false
positives, and below 30,000 average Reviewer tokens on a broader unseen set.

## Latest Result

The completed diagnostic A/B and promotion decision are recorded in
`docs/experiments/logic-review-digest-v2-results.md`. Digest v2.1 remains shadow
only and is not connected to automatic repair.
