"""Versioned commercial warning and tenant admission policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from manim_quality.delivery.evidence import content_hash
from manim_quality.orchestrator.models import (
    WarningPolicyDecision,
    WarningRecord,
    WarningStage,
)


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class WarningRule:
    code: str
    risk: RiskLevel
    stages: Sequence[WarningStage]

    def __post_init__(self) -> None:
        _text(self.code, "code")
        if not isinstance(self.risk, RiskLevel):
            raise TypeError("risk must be RiskLevel")
        stages = tuple(self.stages)
        if not stages or len(set(stages)) != len(stages):
            raise ValueError("stages must be non-empty and unique")
        if any(not isinstance(stage, WarningStage) for stage in stages):
            raise TypeError("stages must contain WarningStage values")
        object.__setattr__(self, "stages", stages)


@dataclass(frozen=True, slots=True)
class TenantLimits:
    max_tokens_per_job: int
    max_concurrent_jobs: int

    def __post_init__(self) -> None:
        _positive(self.max_tokens_per_job, "max_tokens_per_job")
        _positive(self.max_concurrent_jobs, "max_concurrent_jobs")


@dataclass(frozen=True, slots=True)
class AdmissionDecision:
    allowed: bool
    reasons: tuple[str, ...]
    policy_version: str
    limits: TenantLimits


class CommercialWarningPolicy:
    def __init__(
        self,
        *,
        version: str,
        warning_rules: Sequence[WarningRule],
        hard_blockers: frozenset[str],
        default_limits: TenantLimits,
        tenant_limits: Mapping[str, TenantLimits] | None = None,
    ) -> None:
        _text(version, "version")
        rules = tuple(warning_rules)
        if any(not isinstance(rule, WarningRule) for rule in rules):
            raise TypeError("warning_rules must contain WarningRule values")
        codes = [rule.code for rule in rules]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate warning rule")
        if not isinstance(hard_blockers, frozenset):
            raise TypeError("hard_blockers must be frozenset")
        for code in hard_blockers:
            _text(code, "hard_blocker")
        if not isinstance(default_limits, TenantLimits):
            raise TypeError("default_limits must be TenantLimits")
        overrides = dict(tenant_limits or {})
        for tenant_id, limits in overrides.items():
            _text(tenant_id, "tenant_id")
            if not isinstance(limits, TenantLimits):
                raise TypeError("tenant limit override must be TenantLimits")
        self.version = version
        self._rules = MappingProxyType({rule.code: rule for rule in rules})
        self._hard_blockers = hard_blockers
        self._default_limits = default_limits
        self._tenant_limits = MappingProxyType(overrides)

    def authorize(
        self,
        stage: WarningStage,
        warnings: tuple[WarningRecord, ...],
        assessment_hash: str,
        request,
    ) -> WarningPolicyDecision:
        if not isinstance(stage, WarningStage):
            raise TypeError("stage must be WarningStage")
        if any(not isinstance(warning, WarningRecord) for warning in warnings):
            raise TypeError("warnings must contain WarningRecord values")
        authorized = bool(warnings) and all(
            self._allows(stage, warning) for warning in warnings
        )
        hashes = tuple(warning.evidence_hash for warning in warnings)
        evidence = content_hash(
            {
                "assessment_hash": assessment_hash,
                "authorized": authorized,
                "job_id": request.job_id,
                "policy_version": self.version,
                "request_hash": request.request_hash,
                "stage": stage.value,
                "warning_codes": [warning.code for warning in warnings],
                "warning_evidence_hashes": list(hashes),
            }
        )
        return WarningPolicyDecision(stage, authorized, hashes, self.version, evidence)

    def admit(
        self,
        tenant_id: str,
        *,
        active_jobs: int,
        used_tokens: int,
        reserved_tokens: int,
    ) -> AdmissionDecision:
        _text(tenant_id, "tenant_id")
        _count(active_jobs, "active_jobs")
        _count(used_tokens, "used_tokens")
        _count(reserved_tokens, "reserved_tokens")
        limits = self._tenant_limits.get(tenant_id, self._default_limits)
        reasons = []
        if active_jobs >= limits.max_concurrent_jobs:
            reasons.append("concurrency_limit")
        if used_tokens + reserved_tokens > limits.max_tokens_per_job:
            reasons.append("token_ceiling")
        return AdmissionDecision(not reasons, tuple(reasons), self.version, limits)

    def limits_for(self, tenant_id: str) -> TenantLimits:
        _text(tenant_id, "tenant_id")
        return self._tenant_limits.get(tenant_id, self._default_limits)

    def _allows(self, stage: WarningStage, warning: WarningRecord) -> bool:
        if warning.code in self._hard_blockers:
            return False
        rule = self._rules.get(warning.code)
        return rule is not None and rule.risk is RiskLevel.LOW and stage in rule.stages


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a versioned non-empty string")


def _positive(value: object, name: str) -> None:
    _count(value, name)
    if value == 0:
        raise ValueError(f"{name} must be positive")


def _count(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
