from __future__ import annotations

import pytest

from manim_quality.contracts import DeliveryDecision, QualityResult


def _result(
    decision: DeliveryDecision,
    warnings: list[str],
) -> QualityResult:
    delivered = decision in {
        DeliveryDecision.ACCEPT,
        DeliveryDecision.ACCEPT_WITH_WARNING,
    }
    return QualityResult(
        job_id="job-1",
        decision=decision,
        accepted_revision_id="rev-1" if delivered else None,
        final_code_ref="artifact://final.py" if delivered else None,
        final_render_manifest_ref="artifact://render.json" if delivered else None,
        certificate_ref="artifact://certificate.json",
        warnings=warnings,
        token_usage={},
        timings_ms={},
    )


def test_accept_rejects_warnings() -> None:
    with pytest.raises(ValueError, match="ACCEPT.*warnings"):
        _result(DeliveryDecision.ACCEPT, ["residual risk"])


@pytest.mark.parametrize("warnings", [[], [""]])
def test_accept_with_warning_requires_non_empty_warning(
    warnings: list[str],
) -> None:
    with pytest.raises(ValueError, match="warnings"):
        _result(DeliveryDecision.ACCEPT_WITH_WARNING, warnings)


def test_accept_with_warning_preserves_non_empty_warnings() -> None:
    result = _result(DeliveryDecision.ACCEPT_WITH_WARNING, ["residual risk"])

    assert result.warnings == ("residual risk",)


@pytest.mark.parametrize(
    "decision",
    [DeliveryDecision.REGENERATE, DeliveryDecision.HOLD, DeliveryDecision.FAILED],
)
@pytest.mark.parametrize("warnings", [[], ["non-delivery diagnostic"]])
def test_non_delivery_decisions_allow_optional_non_empty_warnings(
    decision: DeliveryDecision,
    warnings: list[str],
) -> None:
    result = _result(decision, warnings)

    assert result.to_dict()["warnings"] == warnings
