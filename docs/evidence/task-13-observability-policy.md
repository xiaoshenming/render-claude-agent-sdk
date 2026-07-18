# Task 13 Evidence: Observability And Commercial Policy

## Scope

Task 13 adds versioned warning authorization, tenant admission limits,
commercial quality metrics, alert evaluation, Agent usage projection, and a
tamper-evident audit port. It does not claim that launch targets have been met.

## Test-First Evidence

- Delivery policy tests initially failed because
  `manim_quality.delivery.policy` did not exist.
- Observability tests initially failed because
  `manim_quality.observability` did not exist.
- Focused verification after implementation:
  `python -m pytest -q tests/unit/observability
  tests/unit/test_delivery_policy.py
  tests/integration/test_api_commercial_policy.py`.

## Implemented Guarantees

- Only versioned, explicitly allowlisted, low-risk warning codes can be
  authorized, and authorization is scoped to the Logic or Layout stage.
- Hard blockers, unknown warnings, empty warning sets, and stage mismatches fail
  closed.
- Tenant concurrency limits are applied at API intake. Tenant token ceilings are
  exposed through the same policy for pre-Agent admission by the execution
  harness.
- Agent usage is persisted to the existing usage sink before token and latency
  metrics are projected. Input, output, cache-read, and cache-write tokens remain
  separately visible.
- Metrics cover every signal required by the implementation plan and remain
  tenant scoped.
- Audit records are idempotent, payload bounded, secret/source fields rejected,
  and hash chained per tenant and job.
- Alerts use versioned thresholds. Any accepted-worse, duplicate, or rollback
  event is alertable under the launch policy.

## Deliberate Boundaries

- The initial warning allowlist is empty. No warning code may be activated until
  Task 14 holdout evidence certifies it.
- `MetricsAggregator` is an in-process projection and `AuditRepository` is a
  persistence port. Production metric export, durable audit storage, dashboard
  wiring, and alert routing depend on deployment infrastructure and remain launch
  work.
- Token limits must be checked by the worker before every Agent call. This task
  supplies the versioned policy; Task 14 validates the full execution path under
  load and outage injection.
- Dashboard definitions and launch thresholds are contracts in
  `docs/commercial-quality-policy.md`, not evidence that production targets are
  already achieved.

## Acceptance Criteria Trace

| Requirement | Evidence |
| --- | --- |
| Hard blockers and warning table | `tests/unit/test_delivery_policy.py` |
| Per-tenant ceilings and concurrency | unit policy tests and `tests/integration/test_api_commercial_policy.py` |
| Required commercial metrics | `tests/unit/observability/test_metrics.py` |
| Versioned alerts | alert tests and commercial policy document |
| Tamper-evident bounded audit | `tests/unit/observability/test_audit.py` |
| Agent token/latency projection | usage sink test |

## Residual Launch Risk

Commercial readiness still requires frozen holdouts, the 100-job concurrency
test, a real Linux render capacity run, shadow production submissions, and a
recorded launch/rollback decision. Those are Task 14 acceptance evidence.
