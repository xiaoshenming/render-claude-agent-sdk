# Logic Known-Bad Set

This directory stores the primary frozen hash manifest for 29 blind medium,
hard, and expert logic/geometry mutations. One smoke-tuned case is excluded by
`selection.json` and replaced from an independent source pack, preserving a
30-case known-bad cohort. The replacement is mutation-independent but may share
an original production source with another case. Ground truth is evaluation-only and must never be
included in Reviewer prompts or readable paths.

`MANIM_LOGIC_EVAL_PACKS_ROOT` points to the parent logic-data directory; frozen
artifact paths include the `mutation_eval_packs_20260708` prefix.

All 30 cases are scored. Errors and unsupported outcomes stay in the false
negative denominator rather than being removed from the report.
