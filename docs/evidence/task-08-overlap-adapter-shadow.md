# Task 8 Overlap Adapter Shadow Evidence

## Decision

Task 8 proves that the frozen overlap package can produce bounded candidate
repairs behind a platform-owned adapter. It does not certify final videos. Two
of ten frozen production-risk cases passed a raw independent blocking recheck.
A third becomes policy-eligible after replaying the versioned impact classifier;
all three still require Task 9 render validation and Task 10 orchestration.

The repair threshold remains independent of sample IDs. Impact policy v1
downgrades only short text/formula objects fully contained and almost exactly
centered inside area-bearing shapes. It records the observation as an ambiguous
warning instead of forcing the Agent to destroy a likely diagram relationship.

## Integration Boundary

- The platform loads only a manifest-verified materialization of the frozen
  vendor archive.
- The vendor Agent retains only Claude Agent SDK `Read` and `Edit` tools.
- Normal mode exposes `layout_issue_digest.json` and `core_candidate.py`, not
  the full candidate or full detector context.
- Full-candidate fallback is allowed only after a proven no-edit Core attempt,
  high residual blocking and sufficient remaining budget.
- A vendor success status creates evidence only. Platform semantic checks and
  an independent detector recheck remain mandatory.
- Candidate and evidence paths are confined to the request evidence root.
- Usage, round, path, checker and SDK inconsistencies fail closed.
- Per-call capacity is initially generous at 300,000 tokens, but is passed to
  SDK `task_budget` as an execution-time boundary and remains job-budget bound.

The upstream archive remains unchanged. A minimal compatibility release adds
only public `candidate_mode=core|full` and SDK `task_budget` wiring. Platform
production code no longer imports vendor-private controller modules.

## Frozen Sources

| Source | Identity |
| --- | --- |
| Upstream archive SHA-256 | `53357fc785cf8896c6ad0878ca68e9a0713114a47efc9eadbdc2cdd05f524221` |
| Active compatibility archive SHA-256 | `7af3fb512fe8ddf08da1f1687e7f0fdd0f5b4741a9ac4f17612987a35e02d6c7` |
| Materialized content identity | `658bad46d52c87b3cb991284c101b43ee8a741c35181845ea983aa5301393c54` |
| Vendor SDK version | `0.2.115` |
| Dataset manifest SHA-256 | `6b343f8fcd9d304b72d38d05adecf7d6a0a5a4965c46ad759a0562317fd6a582` |
| Archived three-case summary SHA-256 | `c7e5df1b4a361788d231aec05077c3d54689744661ec211f1ed92f3de06d6aee` |

The evaluated set is the first ten entries in the frozen dataset manifest. It
is a frozen regression corpus of real production risks, not an untouched
holdout. The repository manifest references external samples by identity and
does not copy production code.

## RED To GREEN

The initial adapter test failed because `manim_quality.layout` did not exist.
Successive focused runs covered vendor mapping, budget/path failures, semantic
scope, fallback and follow-up behavior. The test-file split then exposed a real
collection failure caused by relative imports outside a package. Adding the
integration test package restored collection.

Two general semantic-policy regressions were recorded independently of sample
IDs:

- dimension-guarded `width`/`height` scaling is presentation-only when its body
  contains only recognized layout calls;
- nested computations inside layout method arguments remain semantic and may
  not be erased from the fingerprint.
- a short centered label fully contained by an area-bearing shape is
  record-only, while long content and edge-crossing labels remain blocking;
- public full-candidate mode and SDK task budget were first observed failing in
  the upstream package, then passing in the compatibility release.

The final overlap-focused run before full gates was `38 passed`. The frozen
vendor suite was `237 passed, 6 deselected` on Windows; the deselections are
pre-existing POSIX mode/symlink tests unavailable on this host.

The final repository gate was `946 passed, 4 skipped`; Ruff, format, engineering
standards, vendor verification and `git diff --check` also passed.

## Ten-Case Result

| Case | Baseline | Vendor result | Platform/external result | Tokens | Agent turns |
| --- | ---: | --- | --- | ---: | ---: |
| 01 | 24 | degraded to 17 | reject: residual above policy | 77,699 | 7 |
| 02 | 23 | clean to 0 | reject: removed source `.copy()` and changed animation lifetime | 43,560 | 4 |
| 03 | 11 | clean to 0 | candidate; independent 20-snapshot recheck found 0 blockers | 35,646 | 4 |
| 04 | checker error | not called | unresolved: undefined `title_zone` | 0 | 0 |
| 05 | 23 | reported clean | historical budget reject; current semantic guard also rejects animation rewrite | 281,190 | 6 |
| 06 | checker error | not called | unresolved: missing `get_points()` | 0 | 0 |
| 07 | checker error | not called | unresolved baseline execution | 0 | 0 |
| 08 | 14 | degraded to 2 | policy candidate: 3 raw events replay to 0 blocking + 3 warnings | 43,880 | 5 |
| 09 | 10 | clean to 0 | candidate; independent blocking recheck found 0 blockers | 48,730 | 6 |
| 10 | checker error | not called | unresolved baseline execution | 0 | 0 |

The Case 08 patch changes formula-group scaling and canvas placement only. Its
independent probe produced three raw events: `c²`, `a²` and `b²` centered inside
their polygons. Replaying the general impact classifier produced zero blockers
and three persisted warnings. The counterexample test keeps a label crossing a
shape edge blocking.

### Metrics

| Metric | Result |
| --- | ---: |
| Frozen known-bad cases | 10 |
| Baseline checker supported | 6/10 (60.00%) |
| Baseline checker/code failures | 4/10 (40.00%) |
| Agent attempts | 6 |
| Vendor internal improvement | 6/6 |
| Raw externally clean blocking candidates | 2/10 (20.00%) |
| Current policy-eligible candidates | 3/10 (30.00%) |
| Current policy-eligible among supported | 3/6 (50.00%) |
| Accepted-worse | 0 |
| Agent repair rounds | one per attempted case |
| SDK turns | 32 total |
| Tool calls | 13 Read + 12 Edit |

No unsupported case is removed from the overall denominator. Vendor-reported
clean/degraded status was positive in all six attempted cases, while the outer
boundary retained only three candidates after versioned impact classification.
This is direct evidence that the Agent cannot be its own acceptance authority.

## Usage And Context

| Usage | Tokens |
| --- | ---: |
| Input | 303,946 |
| Output | 226,759 |
| Cache read, already represented in provider usage | 121,724 |
| Accounted total | 530,705 |
| Mean per Agent attempt | 88,451 |
| Median per Agent attempt | 46,305 |
| Highest case | 281,190 |
| Two raw externally clean candidates | 84,376 total; 42,188 mean |

These figures are from the upstream-package ten-case run. The high mean is
dominated by Case 05. The final compatibility release uses an execution-time
SDK task budget with an intentionally generous 300,000-token per-call ceiling.
It starts with one vendor repair round and does not grant another call merely
because the first result improved.

A real compatibility-release SDK smoke accepted `task_budget=30,000`, completed
one edit round, consumed 13,940 tokens and returned `SUCCESS_CLEAN`. The smoke
proves protocol compatibility and bounded execution, not layout quality.

For Case 03, the original candidate plus layout context contained 59,538
characters. The Agent-readable issue digest plus Core candidate contained
10,938 characters, an 81.6% reduction. The Agent read only the 7,073-character
issue digest and 3,865-character Core candidate before editing. Full source,
prelude and uncompressed layout facts were not readable in normal mode.

## Known-Good Replay

Two independently clean repaired outputs were replayed through the materialized
vendor public API with clean checker evidence. Both returned `no_change`, used
zero Agent rounds and zero tokens, and produced no edit. This is a small smoke
set, not a statistically sufficient false-positive holdout.

## Archived Baseline

The archived three-case SDK run improved all three cases, cleared one, consumed
161,425 tokens and did not have the platform semantic, path or independent
acceptance boundary. Its checker counts differ from the current detector, so it
is retained as historical context rather than used for a direct rate claim.

## Residual Risk

- Four of ten real samples cannot enter the detector because their source or
  local evaluation environment fails first. They remain unresolved.
- Impact policy v1 treats only short, almost exactly centered containment as an
  explicit product-approved ambiguous warning. Other observations stay blocking
  until a frozen annotated evaluation or Task 9 render evidence supports change.
- The semantic projection is deliberately conservative and is not a proof of
  mathematical equivalence. It rejects uncertain edits and still requires
  external checks.
- Case 05 demonstrates a severe token tail in the upstream package. The new SDK
  task budget was protocol-smoked but the 300,000-token boundary has not yet
  been stress-tested on that exact case.
- Task 8 did not render final videos. Candidate visual correctness and slice
  consistency belong to Task 9 and Task 10.
- Windows evaluation required a local relative-path `dvisvgm` adaptation and a
  process-local credential-file permission accommodation. Neither change is in
  production code or the frozen vendor source.
