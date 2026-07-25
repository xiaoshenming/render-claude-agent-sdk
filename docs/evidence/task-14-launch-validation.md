# Task 14 Evidence: Holdout, Load, And Launch Validation

## Decision

`launch-v1` is **HOLD**. The harness is operational, but the current Logic Agent
quality and missing deployment evidence do not meet commercial auto-repair
requirements. This is a valid fail-closed launch result, not a completed launch.

## Fresh Runs

| Run | Result |
| --- | --- |
| Frozen logic manifests | 3 packs, 36 cases verified |
| Live Logic Reviewer probe | 10 cases, 40% bad-case recall, 20% good-case false positives |
| Live Logic repair probe | 3 attempted, 2 candidate-ready, 0 exact target restorations |
| Modification E2E | 16 passed |
| Concurrent fake load | 100 completed, 0 dead letters, 0 duplicates, 2969 ms |

The live Reviewer used `443,651` tokens total (`44,365.1` average) and the repair
probe used another `95,816`. The provider model was
`gemini-3.5-flash-high` through Claude Agent SDK `0.2.115`.

## Safety Interpretation

- Two known-bad cases were missed as PASS. One additional bad case was blocked
  for human review but did not hit the expected target error.
- One known-good case was incorrectly sent to repair. The Coder result was
  rejected, so the outer harness prevented an over-edit from promotion.
- Two known-bad repair candidates passed the internal path far enough to become
  candidate-ready, but neither restored the frozen reference target. They are
  not accepted repairs.
- The overlap regression remains useful for adapter safety, but it is neither a
  blind holdout nor final video proof.

## Evidence Binding

- Reviewer report:
  `sha256:3b7ebfc8b723b4b7cb93e6478d795736d0e42f09532f2a5fc7e98f2bf3e1d128`
- Repair report:
  `sha256:be13161ddf915549e878792c841b31230468d6416cfe62dfa7b1f0914bd73fbc`
- Fake-load report:
  `sha256:c00a6bad0c546e52b61968076838d71187d561dcebcd9ce102f3dd7339ea7d39`

Full per-case reports remain in ignored local storage under
`evals/reports/launch-v1/`; committed evidence contains only hashes, metrics,
selection rules, and the decision.

## Remaining Launch Work

1. Improve general Reviewer evidence and issue contracts, then run a new frozen
   version rather than tuning against these ten cases.
2. Add final render-based verification to the repair shadow path.
3. Build an independent untouched overlap holdout with accepted visual labels.
4. Run Linux real-render capacity and production shadow canary.
5. Connect durable PostgreSQL/RabbitMQ/object storage, metrics, audit, dashboard,
   and alert backends before declaring the platform production-deployed.
