# Geometry Inspector v1 Evaluation

This frozen pack measures the deterministic tool boundary, not Agent skill. It
contains 11 server-derived production geometry contradictions and 11 known-good
original generated candidates. Production descriptions and mutation repair hints
are deliberately excluded.

The committed selection stores only IDs, relative artifact paths, hashes, Scene
IDs, relation labels, logical operands, and private expected facts. The evaluation
runner never adds relation labels or private truth to a Reviewer prompt.

Run locally:

```powershell
$env:PYTHONPATH='src'
python -m evals.run_geometry_inspector_eval `
  --production-root D:\geometry_logic_gate_mvp\datasets\prod_hard_logic_fixable_50_v1 `
  --control-root C:\Users\Admin\Desktop\逻辑工具\mutation_eval_packs_20260708\geo30_mutation_v5_blind `
  --output evals\reports\geometry-inspector-v1\tool-report.json
```

`known` answers must be 100% accurate. `unknown` is an explicit support gap and
is counted against coverage, but it is safer than a guessed fact. The current
static adapter is expected to leave helper-built, dynamic, and 3D objects unknown;
the renderer snapshot adapter is the production path for reducing that gap.
