# Commercial Quality Policy

Policy version: `commercial-v1`

This policy is independent from model, prompt, schema, validator, and tool
versions. Changing a prompt never changes commercial acceptance authority.

## Delivery Authority

Only the orchestrator and deterministic final consistency gate may authorize
delivery. Agent output is evidence, never acceptance.

| Condition | Commercial result |
| --- | --- |
| All mandatory certificates and hashes agree, no warning | `ACCEPT` |
| Every warning is in the active low-risk allowlist and exact evidence is bound | `ACCEPT_WITH_WARNING` |
| Repairable blocker with remaining bounded route | `REGENERATE` |
| Unknown, conflicting, high-risk, stale, or unverifiable evidence | `HOLD` |
| Infrastructure or contract failure with no retry route | `FAILED` |

The initial production warning allowlist is empty. A warning code becomes active
only after an independent holdout shows that it is presentation-only, has no
effect on answer, geometry, timing semantics, narration, assets, or visibility,
and names the allowed Logic/Layout stage in a new policy version.

Hard blockers can never be downgraded to warnings. They include answer mismatch,
geometric contradiction, missing proof step, stale evidence, code/video or
revision/manifest mismatch, unresolved blocking overlap, uncertain dependency
impact, partial user-modification intent, and any unknown warning code.

## Tenant Limits

Every tenant has a versioned `TenantLimits` record:

- maximum active quality jobs;
- maximum total quality-Agent tokens per job.

Admission is denied before another Agent call when either hard cap would be
exceeded. Warning status, repair improvement, priority, and retries never bypass
these caps. Commercial plans may tighten or raise configured limits, but every
value remains finite and centrally enforced.

## Metric Definitions

| Metric | Definition |
| --- | --- |
| First-pass yield | first-pass good jobs / jobs started |
| Sampled good-product rate | blind-review good delivered samples / sampled deliveries |
| Auto-delivery rate | automatically delivered jobs / jobs started |
| Logic trigger rate | jobs requiring logic intervention / jobs started |
| Overlap trigger rate | jobs requiring overlap intervention / jobs started |
| Repair uplift | externally verified successful repairs / repair attempts |
| Accepted-worse rate | delivered candidates judged worse / delivered jobs |
| Manual, HOLD, regeneration rate | each outcome / jobs started |
| User modification rate | post-delivery modification requests / delivered jobs |
| Agent cost and latency | totals and distributions per role and per job |
| Duplicate and rollback count | explicit durable events; never inferred from missing data |

Zero denominators report `0.0` and are marked insufficient-volume on dashboards;
they are not interpreted as proof of perfect quality.

## Launch Targets And Alerts

These are targets, not current achievement claims:

| Signal | Launch target / alert |
| --- | --- |
| Final sampled good-product rate | at least 95% |
| Auto-delivery rate | at least 85% |
| Manual intervention rate | below 5% after regeneration is connected |
| Accepted-worse rate | exactly 0 |
| Average quality-Agent usage | below 25,000 tokens/job, with tail shown separately |
| Duplicate publish/task | 0; page on any confirmed event |
| Stale evidence or revision/video mismatch | 0; page immediately |
| Rollback | alert on any event and group by failure stage |

First-pass yield and logic/overlap trigger rates are segmentation metrics until
the frozen production holdout establishes a baseline. They must not be improved
by disabling mandatory review or raising detector thresholds.

## Dashboards

1. **Production:** volume, first-pass yield, auto-delivery, HOLD, regeneration,
   manual review, final sampled good rate.
2. **Safety:** accepted-worse, stale evidence, hash mismatch, duplicate, rollback,
   warning codes and policy versions.
3. **Agent cost:** tokens and latency by role, route, tenant, job, percentile and
   high-risk tail; cache tokens remain separately visible.
4. **Repair:** logic/overlap triggers, attempts, verified uplift, no-improvement
   stops and exhausted budgets.
5. **Modification:** post-delivery modification rate, preview failures, intent
   fulfillment, regression and child quality-job outcome.

Dashboards consume structured metric and audit events. They never parse prompts
or raw source code, and audit payloads reject secret, authorization, prompt, and
source-code fields.

## Change Control

Every policy change requires a new version, table test, rationale, counterexample,
frozen holdout result, rollout owner, effective time, and rollback version.
Automatic repair or warning delivery remains in shadow mode until Task 14 launch
validation meets the targets above.
