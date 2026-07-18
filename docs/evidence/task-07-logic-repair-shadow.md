# Task 7 Logic Repair Shadow Evidence

## Decision

Task 7 is a stable candidate checkpoint for the Logic Coder and directed
Verifier. It is not a publish certificate. Every `candidate_ready` result still
requires Task 9 render validation and Task 10 orchestration/final recheck.

The final frozen 30 known-bad plus six known-good run produced 19 known-bad
candidates, restored the exact private reference target in 17 of 30 known-bad
cases (56.67%), and left all six known-good candidates unchanged. Two additional
candidates made non-reference edits that the directed Verifier considered
equivalent; they remain unproven until render and final logic validation.

## Ported Boundary

The frozen legacy repair implementation was characterized directly by
`tests/unit/logic/test_legacy_repair_characterization.py`. The platform retains
its useful boundaries:

- Claude Agent SDK remains the executor.
- Coder receives only `Read` and `Edit`; Verifier receives only `Read`.
- Bash, Write, repository exploration and undeclared paths remain unavailable.
- Candidate edits are judged by outer validation, not by Agent completion text.
- Logic repair excludes overlap/layout work.

The legacy literal-line contract was extended to an immutable multi-issue,
multi-Scene `RepairPlan`. The new outer boundary adds an AST diff guard,
display-reachable predicate evidence, targeted deterministic geometry checks,
changed-Scene risk delta scanning, exception-safe rollback, duplicate patch
fusing and a two-attempt ceiling. Attempt two is permitted only after an
issue-bound deterministic validator proves strict progress; Verifier self-report
cannot unlock another attempt.

## Frozen Inputs

Reviewer evidence root:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task6-stabilized-20260711-113619\final-full-30plus6
```

Reviewer report SHA-256:

```text
8C1106EB5B298607749AAE5AB8BF522DFB7EB8E2D7AD03AF0713E250F2EF2EAE
```

Reviewer summary plus per-case bundle SHA-256:

```text
1AB74CB50A48B79B3D21936D9E620A6D6122E3B6222335713331936BE13401A2
```

The repair run reused the frozen Reviewer reports instead of paying for another
review. Private `original_candidate.py` files were available only to the outer
strict scorer and were never placed in an Agent workspace or prompt.

Final evaluated wheel:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task7-wheel-20260711-135919\manim_quality_platform-0.1.0-py3-none-any.whl
```

Wheel SHA-256:

```text
A8E7CA09BAA15FBE37B3EDA6F01654645B0B1190DAFAC2A26618C999EC410722
```

## Final Run

Evidence root:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task7-final-approved-20260711-135937
```

Repair report SHA-256:

```text
EB1E30BD62F83A21D48C5412F427FAF49DF3C19555BAFE7ABB47EF523AD64112
```

The three-worker run completed in 180.3 seconds of wall time.

| Metric | Result |
| --- | ---: |
| Frozen cases | 30 bad + 6 good |
| Known-bad cases entering Coder | 25 |
| Known-good cases entering Coder | 1 |
| Known-bad `candidate_ready` | 19 |
| Exact private-reference restoration | 17/30 (56.67%) |
| Exact restoration among Reviewer target hits | 17/22 (77.27%) |
| Exact restoration among attempted known-bad | 17/25 (68.00%) |
| Candidate-ready but reference-nonexact | 2 |
| Known-good over-edit | 0/6 |
| Upstream Reviewer errors/no report | 3 |
| Coder/guard/Verifier rejection | 6 bad + 1 good |
| Second repair attempts | 0 |
| Render validation | Not run; owned by Task 9 |

### Usage

| Role | Calls | Input | Output | Cache read | Total | Turns | Model rounds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Coder | 26 | 475,272 | 45,176 | 95,270 | 615,718 | 109 | 57 |
| Verifier | 19 | 182,889 | 33,902 | 0 | 216,791 | 57 | 38 |
| Combined | 45 | 658,161 | 79,078 | 95,270 | 832,509 | 166 | 95 |

Average usage was 23,125 tokens per frozen case, 32,020 per attempted repair,
23,682 per Coder call and 11,410 per Verifier call. Usage includes cache reads.

## Bounded Optimization

The first full run used a four-turn Coder cap:

```text
C:\Users\Admin\AppData\Local\manim-quality-private\task7-full-20260711-131849
```

It produced 18 candidates, 15 exact restorations, zero known-good over-edits and
804,600 tokens. Logs showed six cases with successful Edit calls but no remaining
turn for structured completion. The Coder cap was increased to five while the
Verifier remained at four, and the prompt now explicitly permits one initial Read
only. A pre-hardening run produced 22 candidates, 17 exact restorations and
1,003,414 tokens. The final security pass bound resolved citations to changed
lines, fixed numeric-token matching, expanded capability scanning and bound every
per-case Reviewer report. A final hardening pass also rejected underscore token
continuations, tracked dangerous capability aliases and required resolved
Verifier citations to match the original issue's diff hunk, then closed a dormant
dangerous-alias activation gap. The exact final wheel produced 19 candidates, 17
exact restorations and 832,509 tokens. The preceding hardened run produced 21/18;
the one-case difference is recorded as model run variance rather than presented
as a stable gain. Remaining failures repeated Read or Edit, so turn growth stops
at five.

## Residual Risk

- Reviewer recall is still the end-to-end ceiling: eight known-bad targets were
  not detected, and three cases lacked a usable Reviewer report.
- Two non-reference candidate patches may be valid alternatives, but this Task
  does not count them as externally correct.
- A directed Verifier is evidence, not certification. Only later render, recheck
  and orchestration gates may promote a revision.
- This evaluation did not run Manim. Render breakage and visual consistency are
  intentionally deferred to Task 9.
