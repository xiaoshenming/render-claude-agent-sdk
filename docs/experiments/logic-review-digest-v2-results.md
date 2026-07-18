# Logic Review Digest V2 Results

## Decision

Digest v2.1 is a useful shadow candidate, but it is not approved for automatic
repair. It met the diagnostic recall and token targets, but missed the false
positive target and produced one structured-output failure on a known-good case.

This 16-case set is a diagnostic regression set, not an unseen holdout. These
results must not be presented as production or commercial quality evidence.

## Version History

| Version | Prompt | Purpose | Result |
| --- | --- | --- | --- |
| `evidence-v1` | `logic-reviewer-v6` | frozen baseline | rollback remains available |
| `digest-v2` | `logic-reviewer-v7-digest` | first facts-only input | rejected: decision flags were underspecified and bad cases exhausted correction/turn limits |
| `digest-v2-1` | `logic-reviewer-v7.1-digest` | explicit decision invariants and one-read limit | retain for shadow testing only |

Digest v2.1 added no sample names, coordinates, expected mutations, reference
patches, or issue-specific repair rules. The change was limited to generic
output invariants and tool-use bounds.

## Frozen 16-Case Comparison

The evidence-v1 baseline combines the original 10-case report with the six
previously missing cases. Digest v2.1 ran all 16 cases in one invocation with the
same model, SDK, manifests, selection, and five-worker concurrency.

| Metric | Evidence v1 | Digest v2.1 | Change |
| --- | ---: | ---: | ---: |
| Known-bad target recall | 6/10 (60.0%) | 7/10 (70.0%) | +10.0 pp |
| Known-good false-positive rate | 2/6 (33.3%) | 1/6 (16.7%) | -16.7 pp |
| Detection precision | 75.0% | 77.8% | +2.8 pp |
| Unsafe execution errors | 1/16 | 1/16 | unchanged |
| Total tokens | 678,948 | 364,266 | -46.4% |
| Average tokens per case | 42,434 | 22,767 | -46.4% |
| Input tokens | 378,330 | 223,304 | -41.0% |
| Output tokens | 196,411 | 111,548 | -43.2% |
| Cache-read tokens | 104,207 | 29,414 | -71.8% |
| Average turns | 3.25 | 2.94 | -9.6% |
| Average model rounds | 2.25 | 2.00 | -11.1% |
| Average elapsed time | 27.88 s | 18.32 s | -34.3% |

The outer harness metrics are authoritative. Agent claims alone were not counted
as detection or acceptance.

## Failure Analysis

- `MUT002` and `MUT003` were missed coordinate-relation errors. The digest had
  the relevant coordinates, so these are reasoning variance/misses rather than
  missing-input failures.
- `MUT009` was routed to human review but did not cite the mutated target line,
  so the harness did not count it as target detection.
- `GOOD006` proposed a mathematically unnecessary repair: it treated an
  algebraically equivalent simplified area formula as failure to show coordinate
  differences. The output also omitted the required `repairable` field, so the
  outer validator rejected it. The safe failure is counted in the false-positive
  rate.
- Digest v2.1 removed the systemic v2 failure where `needs_repair` was paired
  with `blocked=false`; bad cases could now complete inside the four-turn limit.

## Promotion Gate

Do not connect v2.1 to repair. The next candidate must be evaluated on a new,
locked unseen set and satisfy all of the following:

- recall at least 70%;
- false-positive rate below 10%;
- average Reviewer tokens below 30,000;
- zero structured-output failures;
- no sample-specific prompt or extraction rules.

The next generic hypothesis is to clarify that algebraically equivalent
simplifications satisfy a requested method unless the source explicitly demands
verbatim notation. That hypothesis must be versioned separately and tested on
new positive and negative controls before another full promotion run.

## Evidence Hashes

- Selection SHA-256:
  `25c3e62ad4bbd059d526ed8e862f20ab7684475c1a512082f8ae7cae42d57fad`
- Evidence-v1 original 10 report SHA-256:
  `3b7ebfc8b723b4b7cb93e6478d795736d0e42f09532f2a5fc7e98f2bf3e1d128`
- Evidence-v1 missing-six report SHA-256:
  `a66d3dabceeb3f3dd825989625d8fa9410fea31d83a1c6ff3fca64a2280e3f1f`
- Digest-v2.1 report SHA-256:
  `a564f76043b62895efeeb0b8f326f59df97c6ea9e5268a114d9fc868069a338`
