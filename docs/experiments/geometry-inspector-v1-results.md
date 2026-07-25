# Geometry Inspector v1 Results

## Decision

**Do not promote `digest-v2-2-geometry` to the production Logic Reviewer.**

Keep the deterministic relation kernel, snapshot contract, renderer adapter, and
bounded SDK-tool infrastructure. Keep the Reviewer route Shadow-only. Production
remains on the rollback-safe `digest-v2-1` route.

This decision is evidence-based. The deterministic tool is accurate on facts it
can prove, but the current on-demand Agent integration does not improve recall
and roughly doubles tokens on the frozen five-sample A/B.

## What Was Built

- immutable `geometry-snapshot.v1` and `geometry-fact.v1` contracts;
- exact-first relation kernel for eight generic relations;
- AST-only `static_initial_state` fallback;
- renderer-owned runtime snapshot adapter boundary;
- one in-process SDK tool, `inspect_geometry_relation`;
- per-run tool grants, call limits, timeouts, output-size limits, and result-hash
  audit records;
- Shadow-only `digest-v2-2-geometry` Reviewer route;
- frozen 11-production-error plus 11-known-good tool evaluation pack.

No production prompt or code contains sample IDs, expected mutations, server
error descriptions, expected coordinates, or sample-specific repair branches.

## Deterministic Tool Evaluation

Dataset:

- 11 server-derived production geometry contradictions;
- 11 original known-good generated candidates;
- relation labels and private truth used only by the offline evaluator.

Results:

| Metric | Result |
| --- | ---: |
| Total cases | 22 |
| Known facts | 11 |
| Unknown | 11 |
| Support rate | 50.0% |
| Wrong known facts | 0 |
| Known accuracy | 100.0% |

Production-error support was `4/11`; known-good support was `7/11`. Repeated runs
were identical after excluding elapsed time. The unsupported production cases
depend on helper-built objects, dynamic transforms, 3D relations, or relations
outside v1. They correctly remain `unknown`.

This 100% figure is pack-bounded, not a generalization claim. All 11 controls use
`line_endpoints` and collapse to six unique candidate files; the other relations
still need balanced good controls, near-boundary cases, and runtime-derived
counterexamples before any production claim.

Generated evidence:

`evals/reports/geometry-inspector-v1/tool-report-after-static.json`

## Harness Iterations

Logs, rather than prompt intuition, drove the bounded loop:

1. Initial geometry smoke made three 150-line Reads, never used the geometry
   tool, exhausted four turns, and failed at 43,883 tokens.
2. A generic one-Read policy made the same case succeed at 33,388 tokens, but a
   different case needed a second semantic block and was denied.
3. The policy became two Reads, each clamped to 160 lines. Geometry Shadow was
   given five model rounds and six total tool calls, including StructuredOutput
   and one possible schema correction.
4. Tool result status and SHA-256 were added to persisted audit JSON.
5. Relation-specific operand arity and usage guidance were added. Constructor
   topology already present in the digest was explicitly marked as not requiring
   a redundant geometry call.

These are generic Harness policies. None branches on a sample, object name, line
number, or expected fix.

## Frozen Five-Sample A/B

Both routes used the same model, provider, samples, concurrency, and existing
evidence. The set contained three known-bad cases and two known-good controls.

The reported recall is the legacy Shadow proxy: an issue must cite the frozen
target line, but the metric does not independently prove that the diagnosis text
or relation is correct. Promotion therefore requires per-case private semantic
review in addition to this aggregate, and no promotion claim is based on the
`1/3` figure alone.

| Metric | `digest-v2-1` | `digest-v2-2-geometry` |
| --- | ---: | ---: |
| Detection recall | 1/3 (33.3%) | 1/3 (33.3%) |
| Known-good false positives | 1/2 (50.0%) | 0/2 (0.0%) |
| Failed tasks | 1/5 | 2/5 |
| Total tokens | 115,954 | 231,089 |
| Average tokens/task | 23,191 | 46,218 |

Per-case evidence:

| Case | Baseline | Geometry | Baseline tokens | Geometry tokens |
| --- | --- | --- | ---: | ---: |
| MUT002 point shift | pass | error | 26,961 | 60,658 |
| MUT010 relation swap | needs repair | needs repair | 24,432 | 52,792 |
| MUT013 endpoint swap | path error | Read-limit error | 6,634 | 39,111 |
| GOOD001 | pass | pass | 24,282 | 54,725 |
| GOOD006 | false positive | pass | 33,645 | 23,803 |

Generated evidence:

- `evals/reports/geometry-inspector-v1/ab5-baseline/`
- `evals/reports/geometry-inspector-v1/ab5-geometry/`

## Root Cause

The tool answers a proposed relation correctly; it does not know which relation
the lesson intends. The Reviewer must still infer the expected relation from the
problem and construction. On endpoint samples the model sometimes proposed the
actual wrong endpoints as the expectation, making a true tool result irrelevant.

The in-process MCP transport is not the main token cost. Each sequential Read or
tool call creates another model round with repeated context. Geometry cases used
up to two Reads and two relation calls before StructuredOutput. This raised both
tokens and the chance of exhausting the turn budget.

Static extraction is the other limiting factor. It can safely prove literal
points and direct constructors, but helper methods, runtime transforms, Updaters,
and 3D objects remain unknown. Prompt changes cannot repair missing runtime facts.

## Next Correct Experiment

Do not continue prompt tuning on this route. The next experiment should start
only after the renderer supplies `runtime_checkpoint` or `runtime_final`
snapshots with stable logical IDs and topology references.

Then compare two bounded designs on a fresh holdout:

1. **Compact precomputed facts:** include only high-value, diagnosis-free runtime
   relations already tied to explicit lesson claims or named constructions.
2. **On-demand tool:** retain the single tool only for relations absent from the
   compact fact pack.

The same promotion gates remain:

- zero wrong deterministic known facts;
- at least 15 percentage-point recall improvement on the geometry subset;
- known-good false-positive rate below 10%;
- zero structured or Harness failures;
- average tokens no higher than 25,000;
- average model rounds no higher than 2.2;
- no sample-specific production logic.

Until those gates pass, Geometry Inspector is evidence infrastructure, not a
production delivery gate and not an automatic repair certifier.
