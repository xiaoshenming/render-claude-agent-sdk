# Expected/Actual Relation Probe v1

## Decision

The approach is promising for explicit structural geometry errors, but it is
not ready as a general Logic gate. Keep it in Shadow and continue with
checkpoint-aware runtime capture. Do not promote naive final-state coordinate
comparison.

## Question

Can existing problem/solution input be compiled into explicit expected
relations and compared with named geometry in generated Manim code to find
renderable logic errors without giving an Agent the candidate or a diagnosis?

## Method

- Source: `geo30_mutation_v5` paired mutated/original candidates.
- Expected input: `problem_text.txt` only. Candidate code, mutation type,
  mutation line, and expected fix were hidden from the extractor.
- Extractor: `gemini-3.5-flash-high` through Claude Agent SDK structured output.
- Actual evidence: conservative AST point/line index with symbolic endpoint
  identity and virtual segments between named points.
- Decision: deterministic expected/actual comparison.
- Control: the same contract was evaluated against the untouched original code.

## SDK Extraction

Eleven unique source problems produced valid contracts after replacing the
gateway-incompatible JSON Schema `const` keyword with a single-value `enum`.

| Metric | Result |
| --- | ---: |
| Successful extractions | 11/11 |
| Extracted claims | 87 |
| Total tokens | 108,622 |
| Average tokens | 9,874.7 |
| Average model rounds | 2.0 |
| Average elapsed | 13.46 s |
| Input tokens | 37,432 |
| Output tokens | 71,190 |

Output/reasoning tokens were 65.5% of usage. The current Read-then-submit Agent
shape is unnecessarily expensive for this bounded extraction and should later
be tested as a one-round, no-tool SDK call.

## Detection Evidence

The original eleven-case selection is not a valid renderable-logic benchmark:
several injected mutations crash Manim despite metadata claiming they remain
renderable. For example, `MUT001` references undefined `LEFT_CENTER`; other
endpoint swaps make angle construction lines parallel and raise during render.

Five mutated candidates were locally confirmed to execute through Manim dry
render and had complete enough source relations for comparison:

| Case | Mutation | Target hit | Original flagged |
| --- | --- | ---: | ---: |
| MUT002 | point coordinate shift | yes | no |
| MUT003 | point coordinate shift | yes | no |
| MUT015 | named line endpoint swap | yes | no |
| MUT024 | named line endpoint swap | yes | no |
| MUT026 | point coordinate shift | yes | no |

This is `5/5` target hits and `0/5` control flags, but it spans only three
unique source problems and includes post-hoc renderability filtering. It proves
mechanical feasibility, not holdout generalization.

Across the original eleven selected source problems, the recomputed result was
`3/11` target-line hits with `0/11` original flags and a 60.9% unknown-claim
rate. That aggregate is diagnostic only because the pack mixes unsupported
text/proof mutations, missing plans, and non-renderable injected code.

## Additional Frozen Probes

On 2026-07-12, ten previously unused production `geometry_relation_error`
cases were frozen before evaluation. Their existing deterministic contracts
were adapted into the same relation schema without passing repair hints or old
error descriptions into the comparator. This isolates relation comparison; it
does not test expected-relation extraction.

| Metric | Result |
| --- | ---: |
| Production cases | 10 |
| Cases flagged | 10/10 |
| Contradicted claims | 19 |
| Unknown claims | 0 |

The first run flagged `9/10`; `PLOGIC-010` used point variables such as `A_p`
and `C_p`, which the virtual-segment resolver could not address. Adding the
generic explicit segment form `A_p:C_p` changed the result to `10/10`. No
case-specific identifiers or expected values were added to production code.

A separate end-to-end control used a new source problem,
`MTT06_BASE_r7209_q481`, that was not one of the prior eleven sources. The
untouched source had a successful rendered video. Before detector execution,
the sample was frozen with one display-line mutation: `line_DB` ended at
`p_C` instead of `p_B`. Both original and mutated versions rendered to MP4.

The SDK extracted two explicit claims from the problem and solution:
`AB = DC` and `AC = DB`. The initial comparison exposed a generic alias bug:
mathematical point `A` was treated as different from code variable `p_A`.
After normalizing common point-variable wrappers, using the already extracted
contract rather than another model call, the result was:

| Metric | Result |
| --- | ---: |
| New unique source problems | 1 |
| Mutated target-line hit | yes |
| Original flagged | no |
| Original relations satisfied | 2/2 |
| SDK tokens | 6,565 |
| Model rounds | 2 |
| SDK elapsed | 14.42 s |

This is useful new-source evidence, but one source remains far below the
holdout size needed for promotion.

## Runtime Capture Finding

A Python trace prototype captured `construct()` locals from a real Manim dry
render without modifying candidate code. On one complex original source it
captured 13 named point arrays, 10 named lines, and 57 locals. Compared with
static indexing, unknown claims fell from 25 to 3.

Naively comparing the final locals was unsafe: seven contradictions appeared
on the untouched original. The causes were structural:

1. The final summary scales and moves a `VGroup`, mutating line mobjects while
   the original numpy point variables remain unchanged.
2. Equal-length and midpoint claims may be represented by tick marks in a
   schematic diagram rather than exact coordinate distances.
3. A final snapshot loses the earlier checkpoint where the claimed construction
   was first visible and internally consistent.

## Safe Boundary

Suitable for deterministic contradiction evidence:

- a named line such as `line_AD` has symbolic endpoints other than `A,D`;
- a named point is grossly off an explicitly required supporting line at a
  checkpoint where both are visible;
- explicit parallel/perpendicular topology is grossly violated at that same
  checkpoint;
- a coordinate-graph claim when the axes transform and coordinate semantics are
  captured.

Not suitable for unconditional coordinate certification:

- equal lengths in schematic diagrams;
- midpoint ratios represented only by marks;
- final-state point arrays compared with transformed mobjects;
- proof methods, theorem names, displayed equations, or angle-label semantics.

## Next Experiment

1. Hook `Scene.play` externally and inspect the caller `construct()` frame.
2. Capture named point/line values at each play boundary, not only at Scene end.
3. Evaluate only topology relations while all operands are present and visible.
4. Treat exact metric relations as unknown unless the plan declares a
   scale-certified coordinate construction.
5. Build a fresh frozen pack of at least 20 mutations that are independently
   rerendered before inclusion, paired with untouched originals.
6. Keep semantic claims and unsupported geometry with the mandatory Logic Agent.

Promotion still requires a fresh holdout, less than 10% control false positives,
useful recall, and no sample-specific branches.
