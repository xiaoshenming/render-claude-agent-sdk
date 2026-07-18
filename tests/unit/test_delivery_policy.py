from __future__ import annotations

import pytest

from manim_quality.delivery.policy import (
    CommercialWarningPolicy,
    RiskLevel,
    TenantLimits,
    WarningRule,
)
from manim_quality.orchestrator.models import WarningRecord, WarningStage
from tests.e2e.test_quality_happy_path import digest, execution_request


@pytest.mark.parametrize(
    ("code", "risk", "expected"),
    [
        ("minor_label_spacing", RiskLevel.LOW, True),
        ("answer_mismatch", RiskLevel.HIGH, False),
        ("unknown_warning", None, False),
    ],
)
def test_only_versioned_low_risk_warning_rules_can_authorize(
    code: str, risk: RiskLevel | None, expected: bool
) -> None:
    rules = () if risk is None else (WarningRule(code, risk, (WarningStage.LOGIC,)),)
    policy = CommercialWarningPolicy(
        version="commercial-v1",
        warning_rules=rules,
        hard_blockers=frozenset({"answer_mismatch"}),
        default_limits=TenantLimits(50_000, 4),
    )
    warning = WarningRecord(code, "observed warning", digest(code))

    decision = policy.authorize(
        WarningStage.LOGIC,
        (warning,),
        digest("assessment"),
        execution_request(),
    )

    assert decision.authorized is expected
    assert decision.policy_version == "commercial-v1"


def test_warning_rule_is_stage_scoped() -> None:
    policy = _policy()
    warning = WarningRecord("minor_label_spacing", "spacing", digest("spacing"))

    decision = policy.authorize(
        WarningStage.LAYOUT,
        (warning,),
        digest("assessment"),
        execution_request(),
    )

    assert decision.authorized is False


@pytest.mark.parametrize(
    ("tenant_id", "active", "used", "reserved", "allowed", "reason"),
    [
        ("tenant-a", 1, 10_000, 10_000, True, None),
        ("tenant-a", 2, 10_000, 10_000, False, "concurrency_limit"),
        ("tenant-a", 1, 20_000, 10_001, False, "token_ceiling"),
        ("tenant-b", 3, 20_000, 20_000, True, None),
    ],
)
def test_tenant_token_and_concurrency_limits_are_hard_caps(
    tenant_id: str,
    active: int,
    used: int,
    reserved: int,
    allowed: bool,
    reason: str | None,
) -> None:
    decision = _policy().admit(
        tenant_id,
        active_jobs=active,
        used_tokens=used,
        reserved_tokens=reserved,
    )

    assert decision.allowed is allowed
    assert (reason in decision.reasons) if reason else not decision.reasons


def test_policy_rejects_unversioned_or_duplicate_rules() -> None:
    with pytest.raises(ValueError, match="version"):
        CommercialWarningPolicy(
            version="",
            warning_rules=(),
            hard_blockers=frozenset(),
            default_limits=TenantLimits(1, 1),
        )
    with pytest.raises(ValueError, match="duplicate"):
        CommercialWarningPolicy(
            version="v1",
            warning_rules=(
                WarningRule(
                    "minor_label_spacing", RiskLevel.LOW, (WarningStage.LOGIC,)
                ),
                WarningRule(
                    "minor_label_spacing", RiskLevel.LOW, (WarningStage.LOGIC,)
                ),
            ),
            hard_blockers=frozenset(),
            default_limits=TenantLimits(1, 1),
        )


def test_tenant_limit_lookup_returns_override_or_default() -> None:
    policy = _policy()

    assert policy.limits_for("tenant-a") == TenantLimits(30_000, 2)
    assert policy.limits_for("tenant-b") == TenantLimits(50_000, 4)


def _policy() -> CommercialWarningPolicy:
    return CommercialWarningPolicy(
        version="commercial-v1",
        warning_rules=(
            WarningRule("minor_label_spacing", RiskLevel.LOW, (WarningStage.LOGIC,)),
        ),
        hard_blockers=frozenset({"answer_mismatch", "geometry_contradiction"}),
        default_limits=TenantLimits(50_000, 4),
        tenant_limits={"tenant-a": TenantLimits(30_000, 2)},
    )
