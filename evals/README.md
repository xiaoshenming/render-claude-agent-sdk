# Logic Reviewer Shadow Evaluation

The Task 6 shadow harness evaluates the mandatory read-only Logic Reviewer on
three frozen, hash-verified manifests representing two evaluation cohorts:

- `logic_known_bad`: 29 untouched mutations from the primary blind pack.
- `logic_known_bad_replacement`: 1 untouched mutation from an independent pack.
- `logic_known_good`: 6 independent no-error holdout samples.

The manifests contain private evaluation labels. The Reviewer prompt is built
only from verified candidate artifacts and never receives sample IDs, truth
labels, expected issue types, or repair policies.

## Verify Frozen Inputs

Run from the repository root. The isolated wheel install is intentional: it
verifies the same frozen engine modules that a production package installs and
does not rely on pytest's development-only `pythonpath`.

```powershell
uv run --no-project --isolated --with . python -m evals.run_logic_reviewer_shadow `
  --dataset-root "C:\path\to\logic-datasets" `
  --verify-only
```

The command must report three packs and 36 cases before a model call is allowed.

## Run The Reviewer

Inject provider credentials through controlled runtime configuration. Never
write them into this repository, a command transcript, an evaluation report, or
a fixture. Set the model through `MANIM_QUALITY_REVIEW_MODEL` or `--model`, then
run one new known-bad and one new known-good case before the complete holdout.

```powershell
uv run --no-project --isolated --with . python -m evals.run_logic_reviewer_shadow `
  --dataset-root "C:\path\to\logic-datasets" `
  --output "C:\path\to\private-output" `
  --sample-id "KNOWN_BAD_ID" `
  --sample-id "KNOWN_GOOD_ID" `
  --workers 2
```

Only the outer shadow report defines detection, false-positive, failure,
token, turn, and latency metrics. Agent self-reports are not acceptance proof.
