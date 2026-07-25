"""Immutable commercial metric snapshot models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class MetricKind(StrEnum):
    JOB_STARTED = "job_started"
    FIRST_PASS_GOOD = "first_pass_good"
    SAMPLED = "sampled"
    SAMPLED_GOOD = "sampled_good"
    DELIVERED = "delivered"
    AUTO_DELIVERED = "auto_delivered"
    LOGIC_TRIGGERED = "logic_triggered"
    OVERLAP_TRIGGERED = "overlap_triggered"
    REPAIR_ATTEMPTED = "repair_attempted"
    REPAIR_SUCCEEDED = "repair_succeeded"
    ACCEPTED_WORSE = "accepted_worse"
    MANUAL = "manual"
    HOLD = "hold"
    REGENERATED = "regenerated"
    DUPLICATE_TASK = "duplicate_task"
    ROLLBACK = "rollback"
    USER_MODIFICATION = "user_modification"
    TOKENS = "tokens"
    TOKEN_COMPONENT = "token_component"
    LATENCY_MS = "latency_ms"


@dataclass(frozen=True, slots=True)
class Distribution:
    count: int
    total: int
    maximum: int

    @property
    def average(self) -> float:
        return _ratio(self.total, self.count)


@dataclass(frozen=True, slots=True)
class CommercialMetrics:
    tenant_id: str
    counts: MappingProxyType
    tokens_by_role: MappingProxyType
    latency_by_role: MappingProxyType
    tokens_by_job: MappingProxyType
    latency_by_job: MappingProxyType
    tokens_by_component: MappingProxyType

    @property
    def jobs_started(self) -> int:
        return self._count(MetricKind.JOB_STARTED)

    first_pass_yield = property(
        lambda self: self._rate(MetricKind.FIRST_PASS_GOOD, MetricKind.JOB_STARTED)
    )
    sampled_good_product_rate = property(
        lambda self: self._rate(MetricKind.SAMPLED_GOOD, MetricKind.SAMPLED)
    )
    auto_delivery_rate = property(
        lambda self: self._rate(MetricKind.AUTO_DELIVERED, MetricKind.JOB_STARTED)
    )
    logic_trigger_rate = property(
        lambda self: self._rate(MetricKind.LOGIC_TRIGGERED, MetricKind.JOB_STARTED)
    )
    overlap_trigger_rate = property(
        lambda self: self._rate(MetricKind.OVERLAP_TRIGGERED, MetricKind.JOB_STARTED)
    )
    repair_uplift = property(
        lambda self: self._rate(
            MetricKind.REPAIR_SUCCEEDED, MetricKind.REPAIR_ATTEMPTED
        )
    )
    accepted_worse_rate = property(
        lambda self: self._rate(MetricKind.ACCEPTED_WORSE, MetricKind.DELIVERED)
    )
    manual_rate = property(
        lambda self: self._rate(MetricKind.MANUAL, MetricKind.JOB_STARTED)
    )
    hold_rate = property(
        lambda self: self._rate(MetricKind.HOLD, MetricKind.JOB_STARTED)
    )
    regeneration_rate = property(
        lambda self: self._rate(MetricKind.REGENERATED, MetricKind.JOB_STARTED)
    )
    user_modification_rate = property(
        lambda self: self._rate(MetricKind.USER_MODIFICATION, MetricKind.DELIVERED)
    )
    average_tokens_per_job = property(
        lambda self: _ratio(sum(self.tokens_by_job.values()), self.jobs_started)
    )
    sampled_count = property(lambda self: self._count(MetricKind.SAMPLED))

    @property
    def duplicate_task_count(self) -> int:
        return self._count(MetricKind.DUPLICATE_TASK)

    @property
    def rollback_count(self) -> int:
        return self._count(MetricKind.ROLLBACK)

    def _count(self, kind: MetricKind) -> int:
        return int(self.counts.get(kind, 0))

    def _rate(self, numerator: MetricKind, denominator: MetricKind) -> float:
        return _ratio(self._count(numerator), self._count(denominator))


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator
