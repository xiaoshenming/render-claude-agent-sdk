# Logic Engine MVP

This is a small local tool for preparing, reviewing, repairing, and reporting
render-success Manim logic repair tasks.

It deliberately does not ingest historical issue reports at runtime. Reports can
be used offline to study common issue types, but each repair task must be driven
by the current sample's own files.

## Current Scope

The MVP prepares a narrow repair workdir from one sample:

- `candidate.py`
- `issue.json`
- optional `question.txt`
- optional `problem.md`

It writes:

- `candidate.py`
- `logic_contract_context.json`
- `source_region.md`

It can validate text-level contracts before and after repair.
It can also build a clean `review_input.json`, run an LLM reviewer, convert
verified review facts into repair contracts, call Claude Agent SDK / Claude Code
SDK for constrained edits, and write round-level reports.

## Sample Format

Each sample directory should look like this:

```text
case001/
  candidate.py
  issue.json
  question.txt      optional
  problem.md        optional
  before.mp4        optional, not used yet
```

Minimal `issue.json`:

```json
{
  "issue_type": "final_answer_error",
  "wrong_text": "18",
  "expected_text": "24",
  "explanation": "The final answer should be 24."
}
```

Supported aliases:

- wrong value: `wrong_text`, `wrong`, `actual`, `shown`
- expected value: `expected_text`, `expected`, `correct`, `target`

## Commands

Prepare one sample:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp prepare `
  --sample D:\path\to\case001 `
  --out D:\path\to\prepared
```

Prepare a batch:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp prepare-batch `
  --samples-root D:\path\to\samples `
  --out D:\path\to\prepared
```

Validate a candidate against a contract:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp check `
  --code D:\path\to\candidate.py `
  --contract D:\path\to\logic_contract_context.json
```

Exit code:

- `0`: passed
- `1`: contract still failing

Build reviewer input for the current sample:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp review-input `
  --sample D:\path\to\case001 `
  --out D:\path\to\review_input.json
```

This output includes current-sample facts only: question text, scene classes,
string/formula literals, current-sample manifest evidence, and bounded code
excerpts. It never includes historical issue reports. Manifest evidence is
whitelisted to logic-relevant fields such as `visible_error_description`,
`scene_name`, `error_type`, and `expected_visual_change`; trace fields such as
job ids, code URLs, and server refs are not included.

Validate an enterprise sample pack:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp validate-pack `
  --manifest C:\Users\Admin\Desktop\逻辑工具\logic_engine_samples_20260707_goal19\manifest.csv
```

Audit whether a candidate manifest is still valid as locked holdout:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp audit-holdout `
  --manifest C:\Users\Admin\Desktop\逻辑工具\logic_engine_samples_20260708_locked_holdout18_prod50\manifest.csv `
  --runs-root C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260707_goal18 `
  --out C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260707_goal18\round_3_locked_holdout_readiness\locked_holdout18_prod50_audit.json `
  --min-count 18
```

`audit-holdout` excludes samples that already appeared in prior round
`summary.json` files. This prevents a frozen replay from being reported as a
true locked holdout.

Initialize a traceable baseline run directory:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp init-baseline `
  --samples-root C:\Users\Admin\Desktop\逻辑工具\logic_engine_samples_20260707_goal19\samples `
  --out C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260707_goal19
```

## Runtime LLM Roles

Reviewer:

```powershell
$env:LOGIC_REVIEWER_API_KEY="..."
$env:LOGIC_REVIEWER_BASE_URL="https://api.deepseek.com"
$env:LOGIC_REVIEWER_MODEL="deepseek-chat"
```

Repair agent:

```powershell
$env:LOGIC_AGENT_API_KEY="..."
$env:LOGIC_AGENT_BASE_URL="https://ai.onegodtoken.top"
$env:LOGIC_AGENT_MODEL="gemini-3.5-flash-high"
```

The repair executor must use Claude Agent SDK / Claude Code SDK with an
Anthropic-compatible `v1/messages` backend. Do not implement a separate code
agent over raw HTTP. The SDK runner grants only `Read` and `Edit` tools, blocks
`Bash` and `Write`, and edits only the prepared run workdir.

Reviewer issue quality gate:

- every retained issue must include `issue_type`
- every retained issue must include `evidence`
- every retained issue must include `wrong_text` or `wrong_claim`
- every retained issue must include either `expected`/`expected_text` or
  `needs_review_reason`
- incomplete issues are discarded before `llm_review.json` is written
- ambiguous complete issues may remain, but must flow to `needs_human_review`
  instead of automatic repair

## Round Flow

Initialize a baseline run:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp init-baseline `
  --samples-root C:\Users\Admin\Desktop\逻辑工具\logic_engine_samples_20260707_goal18 `
  --out C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260707_goal18
```

For each case directory under `round_0_baseline\cases`:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp review-case --case-dir D:\run\cases\case001
python -m tools.logic_engine_mvp.logic_engine_mvp advance-case --case-dir D:\run\cases\case001
python -m tools.logic_engine_mvp.logic_engine_mvp agent-case --case-dir D:\run\cases\case001 --max-turns 6 --max-budget-usd 0.75
```

Write reports:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp report-round --round-dir D:\run
```

Render-check repaired cases:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp render-case `
  --case-dir D:\run\cases\case001 `
  --affected-only `
  --timeout-sec 420
```

`render-case` is a logic-render smoke check. It renders only the Scene classes
touched by `repair_contract.json` source lines when `--affected-only` is used.
It injects a silent TTS shim, short Manim media directory, and minimal placeholder
enterprise image assets so lightweight logic sample packs can be checked without
production TTS credentials or full branded asset bundles. This proves the edited
logic code can render; it does not prove final production asset fidelity.

## Design Boundary

1. LLM reviewer proposes structured issues.
2. Python verifier confirms computable claims.
3. Contract builder writes `logic_contract_context.json`.
4. Repair agent edits `candidate.py`.
5. Validator and render smoke checks decide pass/fail.

The repair agent should not be the only source of truth for correctness.
Current `validation_passed` means the structured repair contract passed.
Audited success additionally requires `render_check.json` with `passed=true`.

Run or dry-run a whole prepared round:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp run-round `
  --round-dir C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260708_locked_holdout18_prod50\round_0_baseline `
  --dry-run `
  --out C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260707_goal18\round_3_locked_holdout_readiness\run_round_dry_run.json
```

Remove `--dry-run` only after `LOGIC_REVIEWER_API_KEY` and
`LOGIC_AGENT_API_KEY` are present in the process environment. `run-round`
resumes from each case's current `case_status.json` stage and uses the existing
reviewer, verifier, SDK agent, validator, render smoke, and report writer.

Freeze the code used for a locked holdout:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp freeze-code `
  --source-root C:\Users\Admin\Desktop\shuxuepai\tools\logic_engine_mvp\logic_engine_mvp `
  --out C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260707_goal18\round_3_locked_holdout_readiness\code_freeze_manifest.json `
  --label round3_locked_holdout_pre_execution
```

Verify the freeze before interpreting holdout results:

```powershell
python -m tools.logic_engine_mvp.logic_engine_mvp freeze-code `
  --source-root C:\Users\Admin\Desktop\shuxuepai\tools\logic_engine_mvp\logic_engine_mvp `
  --verify C:\Users\Admin\Desktop\逻辑工具\logic_engine_runs_20260707_goal18\round_3_locked_holdout_readiness\code_freeze_manifest.json
```
