from __future__ import annotations

from manim_quality.agents.usage import AgentCallRecord, TokenUsage
from manim_quality.observability.metrics import (
    AlertThresholds,
    MetricEvent,
    MetricKind,
    MetricsAggregator,
    evaluate_alerts,
)
from manim_quality.observability.usage_sink import ObservabilityUsageSink


def test_required_commercial_metrics_and_role_job_usage() -> None:
    metrics = MetricsAggregator()
    events = [
        _event(MetricKind.JOB_STARTED, "job-1"),
        _event(MetricKind.JOB_STARTED, "job-2"),
        _event(MetricKind.FIRST_PASS_GOOD, "job-1"),
        _event(MetricKind.DELIVERED, "job-1"),
        _event(MetricKind.AUTO_DELIVERED, "job-1"),
        _event(MetricKind.SAMPLED, "job-1"),
        _event(MetricKind.SAMPLED_GOOD, "job-1"),
        _event(MetricKind.LOGIC_TRIGGERED, "job-2"),
        _event(MetricKind.OVERLAP_TRIGGERED, "job-2"),
        _event(MetricKind.REPAIR_ATTEMPTED, "job-2"),
        _event(MetricKind.REPAIR_SUCCEEDED, "job-2"),
        _event(MetricKind.ACCEPTED_WORSE, "job-1"),
        _event(MetricKind.HOLD, "job-2"),
        _event(MetricKind.DUPLICATE_TASK, "job-1"),
        _event(MetricKind.ROLLBACK, "job-2"),
        _event(MetricKind.USER_MODIFICATION, "job-1"),
        _event(MetricKind.TOKENS, "job-1", value=1_000, role="logic_reviewer"),
        _event(MetricKind.TOKENS, "job-1", value=500, role="logic_coder"),
        _event(MetricKind.LATENCY_MS, "job-1", value=400, role="logic_reviewer"),
    ]
    for event in events:
        metrics.record(event)

    result = metrics.snapshot("tenant-a")

    assert result.first_pass_yield == 0.5
    assert result.sampled_good_product_rate == 1.0
    assert result.auto_delivery_rate == 0.5
    assert result.logic_trigger_rate == 0.5
    assert result.overlap_trigger_rate == 0.5
    assert result.repair_uplift == 1.0
    assert result.accepted_worse_rate == 1.0
    assert result.hold_rate == 0.5
    assert result.duplicate_task_count == 1
    assert result.rollback_count == 1
    assert result.user_modification_rate == 1.0
    assert result.tokens_by_role["logic_reviewer"].total == 1_000
    assert result.tokens_by_job["job-1"] == 1_500
    assert result.latency_by_role["logic_reviewer"].maximum == 400
    assert result.latency_by_job["job-1"] == 400


def test_metrics_are_tenant_scoped_and_zero_denominators_are_safe() -> None:
    metrics = MetricsAggregator()
    metrics.record(_event(MetricKind.JOB_STARTED, "job-a", tenant="tenant-a"))
    metrics.record(_event(MetricKind.JOB_STARTED, "job-b", tenant="tenant-b"))

    tenant_a = metrics.snapshot("tenant-a")
    empty = metrics.snapshot("tenant-c")

    assert tenant_a.jobs_started == 1
    assert empty.jobs_started == 0
    assert empty.first_pass_yield == 0.0


def test_dashboard_alerts_use_versioned_thresholds() -> None:
    metrics = MetricsAggregator()
    metrics.record(_event(MetricKind.JOB_STARTED, "job-1"))
    metrics.record(_event(MetricKind.MANUAL, "job-1"))
    metrics.record(_event(MetricKind.TOKENS, "job-1", value=30_000, role="reviewer"))
    thresholds = AlertThresholds(
        version="alerts-v1",
        min_auto_delivery_rate=0.85,
        max_manual_rate=0.05,
        max_accepted_worse_rate=0.0,
        max_average_tokens_per_job=25_000,
    )

    alerts = evaluate_alerts(metrics.snapshot("tenant-a"), thresholds)

    assert {alert.code for alert in alerts} == {
        "auto_delivery_rate_low",
        "manual_rate_high",
        "average_tokens_per_job_high",
    }
    assert all(alert.threshold_version == "alerts-v1" for alert in alerts)


def test_safety_alerts_fire_on_any_accepted_worse_duplicate_or_rollback() -> None:
    metrics = MetricsAggregator()
    for kind in (
        MetricKind.JOB_STARTED,
        MetricKind.DELIVERED,
        MetricKind.ACCEPTED_WORSE,
        MetricKind.DUPLICATE_TASK,
        MetricKind.ROLLBACK,
    ):
        metrics.record(_event(kind, "job-1"))
    thresholds = AlertThresholds("alerts-v1", 0.0, 1.0, 0.0, 25_000)

    alerts = evaluate_alerts(metrics.snapshot("tenant-a"), thresholds)

    assert {item.code for item in alerts} == {
        "accepted_worse_rate_high",
        "duplicate_task_count_high",
        "rollback_count_high",
    }


def test_absolute_safety_events_alert_before_job_started_projection_arrives() -> None:
    metrics = MetricsAggregator()
    metrics.record(_event(MetricKind.DUPLICATE_TASK, "job-1"))
    metrics.record(_event(MetricKind.ROLLBACK, "job-1"))
    thresholds = AlertThresholds("alerts-v1", 0.85, 0.05, 0.0, 25_000)

    alerts = evaluate_alerts(metrics.snapshot("tenant-a"), thresholds)

    assert {item.code for item in alerts} == {
        "duplicate_task_count_high",
        "rollback_count_high",
    }


def test_agent_usage_sink_preserves_record_and_projects_role_job_metrics() -> None:
    metrics = MetricsAggregator()
    downstream = MemoryUsageSink()
    sink = ObservabilityUsageSink("tenant-a", "job-1", downstream, metrics)
    record = AgentCallRecord(
        "run-1",
        "logic_reviewer",
        "model-v1",
        "review",
        "prompt-v1",
        "schema-v1",
        "tool-v1",
        {"decision": "PASS"},
        (),
        TokenUsage(100, 20, 10, 5),
        1,
        1,
        250,
        None,
    )

    sink.save(record)

    snapshot = metrics.snapshot("tenant-a")
    assert downstream.records == [record]
    assert snapshot.tokens_by_job["job-1"] == 135
    assert snapshot.latency_by_job["job-1"] == 250
    assert dict(snapshot.tokens_by_component) == {
        "input": 100,
        "output": 20,
        "cache_read": 10,
        "cache_write": 5,
    }


def _event(
    kind: MetricKind,
    job_id: str,
    *,
    tenant: str = "tenant-a",
    value: int = 1,
    role: str | None = None,
) -> MetricEvent:
    return MetricEvent(tenant, job_id, kind, value=value, role=role)


class MemoryUsageSink:
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)
