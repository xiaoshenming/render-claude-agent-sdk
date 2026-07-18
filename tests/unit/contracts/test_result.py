from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from manim_quality.contracts import DeliveryDecision, QualityResult


def _result(decision: DeliveryDecision = DeliveryDecision.ACCEPT) -> QualityResult:
    delivered = decision in {
        DeliveryDecision.ACCEPT,
        DeliveryDecision.ACCEPT_WITH_WARNING,
    }
    return QualityResult(
        job_id="job-123",
        decision=decision,
        accepted_revision_id="rev-003" if delivered else None,
        final_code_ref="artifact://final.py" if delivered else None,
        final_render_manifest_ref=(
            "artifact://final-render-manifest.json" if delivered else None
        ),
        certificate_ref="artifact://quality-certificate.json",
        warnings=["minor residual risk"]
        if decision is DeliveryDecision.ACCEPT_WITH_WARNING
        else [],
        token_usage={"logic_reviewer": 1200, "logic_coder": 800},
        timings_ms={"logic": 3500, "layout": 900},
    )


def test_result_is_frozen_slotted_and_roundtrips_stably() -> None:
    result = _result(DeliveryDecision.ACCEPT_WITH_WARNING)

    assert is_dataclass(result)
    assert result.__dataclass_params__.frozen is True
    assert not hasattr(result, "__dict__")
    assert "schema_version" in {item.name for item in fields(result)}
    with pytest.raises(FrozenInstanceError):
        result.job_id = "changed"  # type: ignore[misc]

    payload = result.to_dict()
    restored = QualityResult.from_dict(payload)

    assert restored == result
    assert payload["decision"] == "ACCEPT_WITH_WARNING"
    assert json.dumps(restored.to_dict(), separators=(",", ":")) == json.dumps(
        payload, separators=(",", ":")
    )


def test_result_deep_freezes_usage_timings_and_warnings() -> None:
    warnings = ["warning-1"]
    token_usage = {"reviewer": 10}
    timings_ms = {"reviewer": 20}
    result = QualityResult(
        job_id="job-123",
        decision=DeliveryDecision.ACCEPT_WITH_WARNING,
        accepted_revision_id="rev-003",
        final_code_ref="artifact://final.py",
        final_render_manifest_ref="artifact://render.json",
        certificate_ref="artifact://certificate.json",
        warnings=warnings,
        token_usage=token_usage,
        timings_ms=timings_ms,
    )

    warnings.append("mutated")
    token_usage["reviewer"] = 999
    timings_ms["reviewer"] = 999

    assert result.warnings == ("warning-1",)
    assert result.to_dict()["token_usage"] == {"reviewer": 10}
    assert result.to_dict()["timings_ms"] == {"reviewer": 20}
    with pytest.raises(TypeError):
        result.token_usage["other"] = 1  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda payload: payload.pop("schema_version"), "schema_version"),
        (
            lambda payload: payload.__setitem__("schema_version", "unsupported"),
            "schema_version",
        ),
        (lambda payload: payload.__setitem__("decision", "UNKNOWN"), "decision"),
        (lambda payload: payload.__setitem__("extra", True), "unknown field"),
    ],
)
def test_result_from_dict_rejects_invalid_contract_shape(
    mutation: object,
    match: str,
) -> None:
    payload = _result().to_dict()
    mutation(payload)  # type: ignore[operator]

    with pytest.raises((TypeError, ValueError), match=match):
        QualityResult.from_dict(payload)


@pytest.mark.parametrize(
    "missing_field",
    [
        "accepted_revision_id",
        "final_code_ref",
        "final_render_manifest_ref",
        "certificate_ref",
    ],
)
@pytest.mark.parametrize(
    "decision",
    [DeliveryDecision.ACCEPT, DeliveryDecision.ACCEPT_WITH_WARNING],
)
def test_delivery_decisions_require_complete_delivery_evidence(
    decision: DeliveryDecision,
    missing_field: str,
) -> None:
    payload = _result(decision).to_dict()
    payload[missing_field] = None

    with pytest.raises(ValueError, match=missing_field):
        QualityResult.from_dict(payload)


@pytest.mark.parametrize(
    "decision",
    [DeliveryDecision.REGENERATE, DeliveryDecision.HOLD, DeliveryDecision.FAILED],
)
@pytest.mark.parametrize(
    "forbidden_field",
    ["accepted_revision_id", "final_code_ref", "final_render_manifest_ref"],
)
def test_non_delivery_decisions_reject_delivery_artifacts(
    decision: DeliveryDecision,
    forbidden_field: str,
) -> None:
    payload = _result(decision).to_dict()
    payload[forbidden_field] = "must-not-be-present"

    with pytest.raises(ValueError, match=forbidden_field):
        QualityResult.from_dict(payload)


@pytest.mark.parametrize(
    "decision",
    [DeliveryDecision.REGENERATE, DeliveryDecision.HOLD, DeliveryDecision.FAILED],
)
def test_non_delivery_decisions_may_reference_a_failure_certificate(
    decision: DeliveryDecision,
) -> None:
    result = _result(decision)

    assert QualityResult.from_dict(result.to_dict()) == result


@pytest.mark.parametrize(
    "decision",
    [DeliveryDecision.REGENERATE, DeliveryDecision.HOLD, DeliveryDecision.FAILED],
)
def test_non_delivery_decisions_do_not_require_a_certificate(
    decision: DeliveryDecision,
) -> None:
    payload = _result(decision).to_dict()
    payload["certificate_ref"] = None

    assert QualityResult.from_dict(payload).certificate_ref is None


@pytest.mark.parametrize("field_name", ["token_usage", "timings_ms"])
def test_result_rejects_negative_accounting(field_name: str) -> None:
    payload = _result().to_dict()
    payload[field_name] = {"stage": -1}

    with pytest.raises(ValueError, match=field_name):
        QualityResult.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("warnings", "not-an-array"),
        ("token_usage", []),
        ("timings_ms", {"stage": True}),
    ],
)
def test_result_rejects_wrong_collection_and_accounting_types(
    field_name: str,
    value: object,
) -> None:
    payload = _result().to_dict()
    payload[field_name] = value

    with pytest.raises(TypeError, match=field_name):
        QualityResult.from_dict(payload)


def test_non_delivery_certificate_must_be_a_non_empty_string_when_present() -> None:
    payload = _result(DeliveryDecision.HOLD).to_dict()
    payload["certificate_ref"] = 42

    with pytest.raises(TypeError, match="certificate_ref"):
        QualityResult.from_dict(payload)
