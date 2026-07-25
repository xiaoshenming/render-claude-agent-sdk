"""Bounded in-process aggregation of required commercial quality metrics."""

from __future__ import annotations

import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from types import MappingProxyType

from ._metric_models import CommercialMetrics as CommercialMetrics
from ._metric_models import Distribution as Distribution
from ._metric_models import MetricKind as MetricKind
from .alerts import AlertThresholds as AlertThresholds
from .alerts import evaluate_alerts as evaluate_alerts


@dataclass(frozen=True, slots=True)
class MetricEvent:
    tenant_id: str
    job_id: str
    kind: MetricKind
    value: int = 1
    role: str | None = None
    component: str | None = None

    def __post_init__(self) -> None:
        _text(self.tenant_id, "tenant_id")
        _text(self.job_id, "job_id")
        if not isinstance(self.kind, MetricKind):
            raise TypeError("kind must be MetricKind")
        _count(self.value, "value")
        if self.kind in {MetricKind.TOKENS, MetricKind.LATENCY_MS}:
            _text(self.role, "role")
        if self.kind is MetricKind.TOKEN_COMPONENT:
            _text(self.component, "component")


@dataclass(slots=True)
class _Accumulator:
    counts: Counter = field(default_factory=Counter)
    role_values: dict = field(default_factory=lambda: defaultdict(dict))
    job_tokens: Counter = field(default_factory=Counter)
    job_latency: Counter = field(default_factory=Counter)
    token_components: Counter = field(default_factory=Counter)


class MetricsAggregator:
    def __init__(self) -> None:
        self._tenants: dict[str, _Accumulator] = {}
        self._lock = threading.Lock()

    def record(self, event: MetricEvent) -> None:
        if not isinstance(event, MetricEvent):
            raise TypeError("event must be MetricEvent")
        with self._lock:
            data = self._tenants.setdefault(event.tenant_id, _Accumulator())
            if event.kind is MetricKind.TOKENS:
                _add_distribution(data, "tokens", event.role, event.value)
                data.job_tokens[event.job_id] += event.value
            elif event.kind is MetricKind.LATENCY_MS:
                _add_distribution(data, "latency", event.role, event.value)
                data.job_latency[event.job_id] += event.value
            elif event.kind is MetricKind.TOKEN_COMPONENT:
                data.token_components[event.component] += event.value
            else:
                data.counts[event.kind] += event.value

    def snapshot(self, tenant_id: str) -> CommercialMetrics:
        _text(tenant_id, "tenant_id")
        with self._lock:
            data = self._tenants.get(tenant_id, _Accumulator())
            return CommercialMetrics(
                tenant_id,
                MappingProxyType(dict(data.counts)),
                MappingProxyType(_distributions(data, "tokens")),
                MappingProxyType(_distributions(data, "latency")),
                MappingProxyType(dict(data.job_tokens)),
                MappingProxyType(dict(data.job_latency)),
                MappingProxyType(dict(data.token_components)),
            )


def _add_distribution(data, category: str, role: str, value: int) -> None:
    item = data.role_values[category].setdefault(role, [0, 0, 0])
    item[0] += 1
    item[1] += value
    item[2] = max(item[2], value)


def _distributions(data, category: str) -> dict[str, Distribution]:
    return {
        role: Distribution(*values)
        for role, values in data.role_values[category].items()
    }


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")


def _count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
