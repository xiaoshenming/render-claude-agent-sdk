"""Adapter that projects persisted Agent usage into commercial metrics."""

from __future__ import annotations

from manim_quality.agents.usage import AgentCallRecord, UsageSink

from .metrics import MetricEvent, MetricKind, MetricsAggregator


class ObservabilityUsageSink:
    def __init__(
        self,
        tenant_id: str,
        job_id: str,
        downstream: UsageSink,
        metrics: MetricsAggregator,
    ) -> None:
        if not isinstance(downstream, UsageSink):
            raise TypeError("downstream must implement UsageSink")
        if not isinstance(metrics, MetricsAggregator):
            raise TypeError("metrics must be MetricsAggregator")
        self._tenant_id = tenant_id
        self._job_id = job_id
        self._downstream = downstream
        self._metrics = metrics

    def save(self, record: AgentCallRecord) -> None:
        if not isinstance(record, AgentCallRecord):
            raise TypeError("record must be AgentCallRecord")
        self._downstream.save(record)
        self._metrics.record(
            MetricEvent(
                self._tenant_id,
                self._job_id,
                MetricKind.TOKENS,
                value=record.usage.total_tokens,
                role=record.role,
            )
        )
        for component, value in (
            ("input", record.usage.input_tokens),
            ("output", record.usage.output_tokens),
            ("cache_read", record.usage.cache_read_tokens),
            ("cache_write", record.usage.cache_write_tokens),
        ):
            self._metrics.record(
                MetricEvent(
                    self._tenant_id,
                    self._job_id,
                    MetricKind.TOKEN_COMPONENT,
                    value=value,
                    component=component,
                )
            )
        self._metrics.record(
            MetricEvent(
                self._tenant_id,
                self._job_id,
                MetricKind.LATENCY_MS,
                value=record.elapsed_ms,
                role=record.role,
            )
        )
