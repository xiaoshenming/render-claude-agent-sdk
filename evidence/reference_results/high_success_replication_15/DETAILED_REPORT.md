# Manim Quality Platform: High-Success Prompt Replication

Run date: 2026-07-13

## 1. Executive conclusion

This was a fresh 15-task replication using the highest-performing Round 3
prompt selection. It did not reuse generated code or prior job outcomes.

- Raw batch: 14/15 quality releases (93.3%).
- Raw strict releases: 7/15 (46.7%).
- Raw warning releases: 7/15 (46.7%).
- Raw holds: 1/15 (6.7%).
- After bounded infrastructure diagnosis: 15/15 were operationally releasable.
  The held job passed an identical-input Logic Reviewer retry and then passed
  the layout detector cleanly. This adjusted result is not written back into
  the raw report.
- First-pass baseline render: 14/15. One invalid Manim API call was recovered
  by the existing one-shot full regeneration, giving 15/15 renderable baselines.
- Final video files: 15/15 readable H.264, 854x480, 44.53-76.07 seconds.
- Audio: 0/15. These are visual/mathematical quality validation videos, not
  complete commercial products with narration.

The direction is viable. The strongest evidence is not the overall release
number alone: the logic stage found and repaired a real high-severity geometry
contradiction, and two overlap repairs were accepted only after zero-blocking,
semantic, and rerender gates. The largest remaining weakness is overlap repair
acceptance and warning handling, not baseline generation or rendering.

## 2. Configuration

- Worktree: `D:\codex-worktrees\manim_quality_platform\workbench-e2e-45`
- Run root: `D:\manim_quality_platform_runs_20260713\high_success_replication_15`
- Model: `gemini-3.5-flash-high`
- API protocol: Anthropic-compatible `/v1/messages`
- Agent runtime: Claude Agent SDK 0.2.116
- Concurrency: 3 jobs
- Workload: 14 hard and 1 medium-hard task
- Domains: geometry 7, function 4, algebra 2, probability 1, statistics 1
- Prompt selection: ID 95 x4, ID 98 x7, ID 99 x4
- Pipeline: generate -> baseline render -> Logic Reviewer -> optional Logic
  Coder -> overlap detect -> optional overlap Agent -> final rerender gate

## 3. Raw result by task

| Slot | Task | Raw status | Logic | Layout blocking | Tokens | Job time |
| --- | --- | --- | --- | ---: | ---: | ---: |
| slot-031 | geo-011 | deliver | review_pass | 0->0 | 35,878 | 71.9s |
| slot-032 | geo-012 | warning | review_pass | 1->0, patch rejected | 72,617 | 107.0s |
| slot-033 | fun-001 | warning | review_pass | 6->1, patch rejected | 110,160 | 172.1s |
| slot-034 | fun-002 | warning | review_pass | 5->0, patch rejected | 91,784 | 187.5s |
| slot-035 | fun-003 | warning | record_only | 3->2, budget error | 115,600 | 217.7s |
| slot-036 | fun-004 | warning | review_pass | 1->1, no progress | 59,571 | 104.8s |
| slot-037 | alg-001 | deliver | review_pass | 0->0 | 35,614 | 57.4s |
| slot-038 | alg-002 | deliver | review_pass | 2->0, accepted | 85,664 | 159.3s |
| slot-039 | prob-001 | deliver | review_pass | 0->0 | 44,011 | 57.9s |
| slot-040 | stat-001 | warning | review_pass | 10->0, patch rejected | 108,325 | 107.1s |
| slot-041 | geo-001 | deliver | review_pass | 0->0 | 57,186 | 67.1s |
| slot-042 | geo-002 | deliver | review_pass | 1->0, accepted | 105,389 | 149.0s |
| slot-043 | geo-003 | deliver | repaired | 0->0 | 95,154 | 98.4s |
| slot-044 | geo-004 | warning | review_pass | detector error | 44,601 | 83.4s |
| slot-045 | geo-005 | hold | reviewer tool error | not reached | 52,170 | 45.9s |

The sum of per-job elapsed time was 1,686 seconds; with three-way concurrency,
the batch wall time was about 9 minutes 43 seconds.

## 4. Logic-stage evidence

Raw decisions were 12 pass, 1 low-risk record-only, 1 needs-repair, and 1 tool
error. The identical-input retry changed only the tool error to pass.

### Successful real logic repair

`slot-043` claimed that AD was a median and EG was parallel to AC, but its
coordinates made D non-midpoint and gave EG a different slope from AC. The
reviewer cited both the task requirement and exact source lines. The coder then
changed one coordinate block so that:

- B=(-6,-1.8), C=(0,-1.8), D=(-3,-1.8), hence BD=DC.
- A=(-3,1.8), C=(0,-1.8), E=(-3,-0.6), G=(-2,-1.8), hence EG is parallel to AC.

The repaired code rerendered successfully and remained layout-clean. A manual
four-frame comparison also showed a symmetric, coherent construction. This is
the clearest proof in the batch that the Logic Reviewer/Coder path is doing
substantive work rather than merely approving generated code.

### Correct low-risk non-repair

`slot-035` used `d = 2` on the diagram while the derivation used `AB = 2`.
Mathematics remained correct, so the reviewer recorded a low-severity notation
warning instead of spending a repair pass. This matches the intended product
policy: mathematical truth first, minor presentation differences may pass with
evidence.

### Reviewer infrastructure fault

`slot-045` was held because the model requested `candidate.` rather than
`candidate.py`; the path guard correctly refused it. With the same code, task,
video, prompt, and permissions, a single reviewer retry returned `pass` in about
17 seconds using 20,760 tokens. The subsequent layout check was clean. The safe
fix is a bounded retry for recognized read-only tool-format failures, not wider
filesystem permissions.

## 5. Overlap-stage evidence

The raw batch invoked overlap repair eight times. After fixing the probe
encoding and diagnosing `slot-044`, nine jobs had detected blocking overlap.

- Two repairs were fully accepted: `slot-038` (2->0) and `slot-042` (1->0).
- Three repairs reached zero blocking but were rejected by semantic fingerprint:
  `slot-032`, `slot-034`, and `slot-040`.
- One repair reduced 6->1 but hit the one-round cap.
- One reduced 3->2 but exceeded the remaining vendor budget.
- Two made no accepted progress.

Manual review of the three zero-blocking semantic rejects is important:

- `slot-032`: a rigid downward translation of the whole geometry. It rendered
  correctly and appears mathematically safe. This is likely a conservative
  false reject.
- `slot-034`: tick-label spacing and axes grouping changed. It rendered
  correctly and appears safe, though the structural edit was broader than
  necessary.
- `slot-040`: the Agent removed a highlight rectangle and changed row text to
  white on a light background. Some rows became nearly invisible. Rejection was
  correct even though mathematical text was unchanged and blocking became zero.

Therefore, simply relaxing the semantic fingerprint would be unsafe. The next
acceptance layer should recognize provably invariant rigid transforms and label
spacing edits while continuing to block object deletion, replacement, and
animation-mechanism rewrites unless a stronger visual gate approves them.

## 6. Token and step profile

Official raw batch tokens: 1,113,724, average 74,248 per task.

| Stage | Tokens | Share |
| --- | ---: | ---: |
| Generation | 389,307 | 35.0% |
| Logic review | 321,067 | 28.8% |
| Logic repair | 46,099 | 4.1% |
| Overlap repair | 357,251 | 32.1% |

Generation used 68,466 input and 320,841 output tokens. Its output is therefore
the dominant generation cost. Logic review used 209,544 input, 65,834 output,
and 45,689 cache-read tokens across 15 calls. It averaged 3.07 SDK turns and
2.13 observed model rounds. The eight overlap Agent calls used 242,527 input and
114,724 output tokens; cache-read usage was separately reported as 123,326.

Post-batch diagnosis added 51,211 model tokens: 20,760 for the identical-input
Logic Reviewer retry and 30,451 for rerunning the corrected `slot-044` overlap
stage. Local rerenders and layout probes used no model tokens.

## 7. General fixes made during diagnosis

The `slot-044` layout probe completed scene execution but failed while printing
its final JSON because Windows GBK could not encode `=>`. The subprocess Harness
now forces `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1` after stripping secrets.
This is an environment-level fix, not a sample rule.

Verification:

- The new encoding tests failed before the implementation change.
- `test_process_env.py`: 2 passed after the change.
- All workbench E2E unit tests: 20 passed.
- The same `slot-044` source then returned valid JSON and one blocking overlap.

The corrected overlap Agent still made no progress on that sample, so it remains
a genuine warning rather than being promoted to strict success.

## 8. Recommended optimization order

1. Add one retry only for recognized transient/read-only Logic Reviewer tool
   failures. Keep the path guard unchanged. This run shows a direct 14/15 to
   15/15 operational recovery for one extra call.
2. Keep the UTF-8 subprocess fix and add the real `=>` probe case to integration
   regression coverage.
3. Replace the binary semantic fingerprint with a typed patch classifier:
   allow verified rigid translation, scale-preserving translation, and label
   spacing; send object deletion, constructor replacement, formula edits, and
   animation rewrites to strict revalidation or rejection.
4. Require overlap patches to be smaller. `slot-040` proves that zero overlap is
   not enough if the Agent rewrites presentation behavior. Limit the preferred
   edit surface to existing positioning calls first, while retaining the ability
   to escalate when local movement cannot solve a global layout problem.
5. Reduce tokens after repair quality stabilizes. Generation output and overlap
   Agent calls are the largest controllable costs. Do not compress the logic
   digest first; it caught the only blocking mathematical contradiction with a
   modest two model rounds.
6. Separate product metrics permanently: strict release, warning release,
   recoverable infrastructure failure, and final commercial score. Warning
   videos must not be reported as strict quality passes.
7. Run a second independent 15-task replication before changing thresholds.
   The acceptance classifier should be tuned against held-out tasks, never
   against `slot-032`, `slot-034`, or `slot-040` by name or content.

## 9. Artifacts

- Machine report: `report.json`
- Flat report: `report.csv`
- Video comparison page: `before_after.html`
- Raw logs: `run_stdout.log`, `run_stderr.log`
- Diagnostic retries: `diagnostics\slot-044-layout-retry-01` and
  `diagnostics\slot-045-logic-retry-01`
- Repair contact sheets: `diagnostics\visual_checks`
- Rerendered rejected candidates:
  `diagnostics\semantic-rejected-renders`

## 10. Limits of this result

This is strong engineering evidence for the chain, not proof of fully autonomous
commercial delivery. The sample is only 15 tasks, the generation and review
model family are not independent, only one blocking logic repair occurred, seven
raw outputs still carried warnings, and the videos have no audio. A final
customer-facing score and TTS synchronization remain outside this run.
