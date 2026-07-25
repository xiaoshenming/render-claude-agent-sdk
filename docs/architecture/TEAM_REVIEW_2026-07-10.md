# Manim Quality Platform Team Review

- Date: 2026-07-10
- Review mode: three independent architecture, Harness, and quality/cost reviews
- Decision: proceed after closing the P0 contracts below

## Confirmed Requirements

1. The quality platform is an independent workspace at `D:\manim_quality_platform`.
2. Generation remains outside and submits code, render artifacts, problem context,
   planning, assets, and version metadata through a contract.
3. Every publish candidate runs the read-only Logic Reviewer.
4. Every logic-certified revision runs the deterministic overlap detector.
5. Logic and overlap Coders are conditional and produce candidate patches only.
6. The Quality Orchestrator alone owns state, acceptance, rollback, and publish.
7. Every edit creates an immutable revision and version-bound evidence.
8. The final consistency gate is deterministic and contains no LLM call.
9. User modification previews may be lightweight, but approved publish candidates
   re-enter the complete quality flow.
10. The overlap package remains frozen behind a platform adapter.

## P0 Decisions Closed

- Independent platform replaces the earlier Render Worker embedded boundary.
- `RECORD_ONLY` no longer maps directly to logic certification.
- Low confidence is not treated as low risk.
- Approved user modifications run the mandatory full Logic Reviewer again.
- Stage checkpoints replace one ambiguous `last_good_revision` pointer.
- Infrastructure retry has lease, heartbeat, deadline, retry budget, and terminal
  HOLD/dead-letter behavior.
- Vendor repair status never bypasses external render and recheck.

## Why The Claude Agent SDK Route Works Better

The difference is not a single SDK feature. It is the combination of:

- capable code reasoning
- stateless role-specific sessions
- narrow structured Read/Edit tools
- path isolation and hooks
- compact, versioned evidence
- bounded turns and repair attempts
- external compile, render, detector, and validator checks
- best-revision rollback
- complete usage, diff, and evidence logs

Removing the Harness would recreate the failure modes seen with broad shell-based
agents. Rebuilding the same Harness on another framework is possible, but it is
mostly duplicate engineering work.

## What This Architecture Can Solve

- Agent self-certification
- failed patches overwriting good code
- stale detector reports attached to new code/video
- unbounded repair loops and repeated patches
- silent partial user modifications
- duplicate publishing and stale worker writes
- missing token, latency, patch, and acceptance evidence

## What It Does Not Prove Yet

- that the Logic Reviewer has high recall on real production errors
- that every geometry or teaching error is deterministically verifiable
- that the overlap detector has no false negatives
- that video aesthetics, pacing, narration, or animation richness improve
- that the average quality cost is already below the commercial target

The current logic module is a non-production prototype, not a production engine. It can
misclassify empty issues as PASS, plans only the first repairable issue, performs
literal-oriented edits, and has a weak recheck. Those behaviors must not enter the
commercial acceptance path.

## Quality And Cost Strategy

Use four bounded routes:

| Route | Work | Purpose |
| --- | --- | --- |
| Fast | mandatory Reviewer + detector + final gate | clean majority |
| Standard repair | one targeted repair and external verification | clear issues |
| High risk | evidence-backed second attempt or full-context fallback | long tail |
| Exception | regenerate or HOLD | unsafe, unverifiable, or over budget |

This makes speed, accuracy, and cost compatible for the population rather than
forcing one context size and one budget onto every job.

## Launch Evidence Matrix

| Metric | Definition | Initial target |
| --- | --- | ---: |
| Critical logic recall | TP / (TP + FN) on frozen known-bad | >=95%, zero missed critical cases in holdout |
| Logic precision | TP / (TP + FP) | >=90% |
| Known-good over-edit | modified known-good / known-good | <3%, goal <1% |
| Logic repair success | accepted correct repairs / repairable issues | >=80% |
| Overlap detector recall | detected blockers / annotated blockers | >=98% |
| Overlap clear rate | final blocking=0 / triggered repairs | >=80% |
| Accepted-worse rate | accepted but worse / accepted repairs | 0 in holdout, <0.5% online |
| Sampled video good rate | blind good / sampled deliveries | >=90% |
| Automatic delivery | automatic deliveries / renderable jobs | >=85% |
| Quality usage | total quality-Agent tokens / all jobs | average <25k; high-risk tail separate |
| Unit good-product cost | model fees + cache fees + render compute + retries / accepted good videos | versioned business target; high-risk tail separate |
| Clean latency | quality stage wall time | P95 <90 seconds, hardware-adjusted |
| Repair latency | quality stage wall time | P95 <6 minutes, hardware-adjusted |
| Evidence mismatch | stale or mismatched deliveries | 0 |

These are release targets, not current results. The overlap Top10 result supports
continuing the direction, but it is too small and too tuned to prove commercial
generalization. Logic needs frozen known-good and known-bad evaluation with a real
confusion matrix.

## Engineering Gate

The independent workspace root `AGENTS.md` is the mandatory development entry.
Its machine checker enforces source-size limits and legacy-import isolation. The
detailed Harness standard defines roles, permissions, budgets, revisions,
acceptance, evaluation, observability, secrets, and anti-overfitting rules.

No implementation task may weaken these rules without a versioned architecture
decision, tests, and holdout evidence.
