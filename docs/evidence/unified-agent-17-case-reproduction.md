# Unified Quality Agent 17-Case Reproduction

## Baseline identity

- Source commit: `645c873`
- Source tag: `unified-quality-agent-baseline-20260726`
- Model: `gpt-5.6-sol`
- Protocol: Anthropic-compatible Messages through Claude Agent SDK
- Sample archive SHA-256:
  `ef973cb2763cc4835c733e65c62f7dfb95aa3da59113a78a7cb76d8b112cae04`
- Sample count: 17
- Concurrency: 2
- Per-case timeout: 900 seconds
- Maximum turns: 16
- Maximum tool calls: 18

The sample archive, rendered videos, and API credentials are intentionally not
committed. They are external controlled inputs. Do not add a real key to this
repository.

## What this baseline proves

The frozen run executed:

```text
Solution extraction
-> native math_geometry_reviewer
-> native animation_lifecycle_reviewer
-> parent Quality Agent findings and patches
-> real Manim render and ffprobe
-> multi-snapshot BBox inspection
-> conditional layout repair
-> independent rerender and layout inspection
```

Results:

- 13 of 17 cases produced `PROPOSED` candidates.
- 4 of 17 cases failed closed.
- All 13 proposed candidates had a valid independent acceptance video.
- All 13 proposed candidates had zero blocking overlap in the independent
  acceptance layout report.
- Four proposed candidates stopped at R1.
- Nine proposed candidates stopped at R2.
- Successful cases consumed 994,113 total reported tokens, averaging 76,470.

`PROPOSED` does not prove independent mathematical correctness. The current
outer validator verifies real rendering and layout, but does not rerun an
independent post-repair mathematical verifier.

## Environment

Use Python 3.11 for the platform:

```powershell
cd tools\manim_quality_platform
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

The generated Manim samples in this frozen run used a separate Manim-capable
Python runtime. Supply that runtime to `--manim-python`. Supply required project
runtime stubs through `--runtime-python-path`; the Agent cannot read these
paths.

## Credentials

Set credentials only in the process environment:

```powershell
$env:ANTHROPIC_BASE_URL = "https://your-anthropic-compatible-endpoint"
$env:ANTHROPIC_AUTH_TOKEN = "<runtime-secret>"
```

Never put a key in prompts, configuration files, evidence files, or Git.

## Focused verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\agents tests\unit\operator -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe scripts\check_engineering_standards.py
```

Frozen baseline result:

- Agent/operator tests: 176 passed, 1 skipped on Windows symlink privilege.
- Ruff: passed.
- Engineering standards: passed.

The repository-wide suite had three known baseline failures:

1. one stale integration test used removed `read_problem` and `read_candidate`
   tools;
2. one historical holdout manifest hash did not match;
3. one historical vendor source manifest hash did not match.

Do not update frozen hashes merely to make the suite green.

## Batch command

After extracting the controlled sample archive:

```powershell
.\.venv\Scripts\python.exe scripts\run_unified_quality_batch.py `
  --package D:\controlled-input\MathPi_17 `
  --output D:\controlled-output\unified-quality-17 `
  --repo (Get-Location) `
  --model gpt-5.6-sol `
  --manim-python D:\runtime\python.exe `
  --runtime-python-path D:\runtime\runtime_stubs `
  --concurrency 2 `
  --case-timeout 900 `
  --max-turns 16 `
  --max-tool-calls 18
```

## Required per-case evidence

For every `PROPOSED` case, verify:

```text
logs/agent_call.json
logs/subagent-results.json
logs/tool_calls.jsonl
revisions/R0.baseline.py
revisions/R1.logic.py or later revision
output/decision.json
output/proposed_candidate.py
acceptance_runtime/<revision>/ffprobe.json
acceptance_runtime/<revision>/layout_detector.json
```

Acceptance requires:

- a proposed candidate exists;
- ffprobe reports positive duration;
- the acceptance layout report is verified;
- `blocking_count` is zero;
- the decision is bound to the expected revision, code hash, and problem hash.

## Frozen case summary

| Case | Status | Revision | Tokens | Turns | Tools | Final blocking |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 017 | PROPOSED | R2 | 77,058 | 12 | 13 | 0 |
| 022 | PROPOSED | R2 | 76,260 | 12 | 17 | 0 |
| 030 | PROPOSED | R2 | 82,608 | 12 | 16 | 0 |
| 035 | FAILED | - | unavailable | - | limit | - |
| 042 | FAILED | - | unavailable | - | - | remaining |
| 045 | FAILED | - | unavailable | - | - | remaining |
| 047 | PROPOSED | R2 | 92,986 | 12 | 16 | 0 |
| 054 | PROPOSED | R1 | 60,659 | 10 | 13 | 0 |
| 057 | PROPOSED | R1 | 52,859 | 10 | 11 | 0 |
| 058 | PROPOSED | R1 | 60,785 | 10 | 11 | 0 |
| 076 | PROPOSED | R2 | 79,816 | 12 | 13 | 0 |
| 078 | PROPOSED | R2 | 85,216 | 12 | 18 | 0 |
| 080 | PROPOSED | R2 | 107,103 | 13 | 17 | 0 |
| 099 | FAILED | - | unavailable | - | - | remaining |
| 100 | PROPOSED | R2 | 81,773 | 14 | 15 | 0 |
| 108 | PROPOSED | R1 | 48,396 | 10 | 11 | 0 |
| 117 | PROPOSED | R2 | 88,594 | 12 | 13 | 0 |

Failure reasons:

- 035: tool-call hard limit exceeded.
- 042: blocking findings lacked a validated repair revision.
- 045: the current revision retained blocking layout issues.
- 099: blocking findings lacked a validated repair revision.

Failed Agent calls did not persist complete usage records. This is a known
audit defect and failed-case cost must not be treated as zero.

## Reproduction comparison

Compare a new run with this baseline only when:

- the sample archive hash matches;
- the source commit and dependency lock are recorded;
- model, endpoint protocol, budgets, and concurrency are recorded;
- all results are reconstructed from persisted evidence, not Agent claims;
- no prompt, tool, or threshold was tuned against the measured cases.

Model and provider nondeterminism can change individual outcomes. A repeated run
is evidence about stability, not a byte-identical golden-output expectation.
