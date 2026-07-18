# Logic Known-Good Set

This directory stores only a frozen hash manifest. Source code, expected
solutions, and videos remain in the external evaluation pack selected through
`MANIM_LOGIC_EVAL_PACKS_ROOT`.

`selection.json` chooses six real rendered source samples. Samples used during
Task 6 smoke debugging are excluded from this holdout and recorded as tuning data.
The environment root is the parent logic-data directory containing both the
source-sample pack and `mutation_eval_packs_20260708`.

All six cases are scored. Any invented issue counts as a false positive; an SDK
or evidence failure remains in the attempted denominator.
