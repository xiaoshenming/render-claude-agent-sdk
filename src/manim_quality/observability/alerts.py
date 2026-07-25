"""Versioned dashboard alert thresholds for commercial quality metrics."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlertThresholds:
    version: str
    min_auto_delivery_rate: float
    max_manual_rate: float
    max_accepted_worse_rate: float
    max_average_tokens_per_job: float
    min_sampled_good_product_rate: float = 0.95
    max_duplicate_task_count: int = 0
    max_rollback_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("threshold version is required")
        for name in (
            "min_auto_delivery_rate",
            "max_manual_rate",
            "max_accepted_worse_rate",
            "min_sampled_good_product_rate",
        ):
            _rate(getattr(self, name), name)
        if (
            isinstance(self.max_average_tokens_per_job, bool)
            or not isinstance(self.max_average_tokens_per_job, (int, float))
            or self.max_average_tokens_per_job <= 0
        ):
            raise ValueError("max_average_tokens_per_job must be positive")
        for name in ("max_duplicate_task_count", "max_rollback_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class MetricAlert:
    code: str
    observed: float
    threshold: float
    threshold_version: str


def evaluate_alerts(snapshot, thresholds: AlertThresholds) -> tuple[MetricAlert, ...]:
    rate_checks = (
        ()
        if snapshot.jobs_started == 0
        else (
            (
                snapshot.auto_delivery_rate < thresholds.min_auto_delivery_rate,
                "auto_delivery_rate_low",
                snapshot.auto_delivery_rate,
                thresholds.min_auto_delivery_rate,
            ),
            (
                snapshot.manual_rate > thresholds.max_manual_rate,
                "manual_rate_high",
                snapshot.manual_rate,
                thresholds.max_manual_rate,
            ),
            (
                snapshot.accepted_worse_rate > thresholds.max_accepted_worse_rate,
                "accepted_worse_rate_high",
                snapshot.accepted_worse_rate,
                thresholds.max_accepted_worse_rate,
            ),
            (
                snapshot.sampled_count > 0
                and snapshot.sampled_good_product_rate
                < thresholds.min_sampled_good_product_rate,
                "sampled_good_product_rate_low",
                snapshot.sampled_good_product_rate,
                thresholds.min_sampled_good_product_rate,
            ),
            (
                snapshot.average_tokens_per_job > thresholds.max_average_tokens_per_job,
                "average_tokens_per_job_high",
                snapshot.average_tokens_per_job,
                thresholds.max_average_tokens_per_job,
            ),
        )
    )
    absolute_checks = (
        (
            snapshot.duplicate_task_count > thresholds.max_duplicate_task_count,
            "duplicate_task_count_high",
            float(snapshot.duplicate_task_count),
            float(thresholds.max_duplicate_task_count),
        ),
        (
            snapshot.rollback_count > thresholds.max_rollback_count,
            "rollback_count_high",
            float(snapshot.rollback_count),
            float(thresholds.max_rollback_count),
        ),
    )
    return tuple(
        MetricAlert(code, observed, threshold, thresholds.version)
        for failed, code, observed, threshold in (*rate_checks, *absolute_checks)
        if failed
    )


def _rate(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not 0 <= float(value) <= 1:
        raise ValueError(f"{name} must be between zero and one")
