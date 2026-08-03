import pytest

from manim_quality.assurance.policy import RawAgentAssessment, apply_assurance_policy


def test_policy_adjustment_is_versioned_hashed_and_revalidated() -> None:
    reports, output = _contract()

    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")

    assert adjusted.policy_version == "final-assurance-policy-v1"
    assert len(adjusted.policy_sha256) == 64
    assert adjusted.raw_sha256 == adjusted.adjusted_sha256


def test_policy_rejects_invalid_adjusted_contract() -> None:
    reports, output = _contract()
    output["tool_receipts"][0]["status"] = "risk"

    with pytest.raises(ValueError, match="receipt status"):
        apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")


def _contract():
    names = (
        "inspect_artifact", "inspect_execution", "inspect_code_review",
        "inspect_layout", "inspect_risk_frames", "inspect_tts",
        "inspect_consistency",
    )
    reports = {
        name: {"tool": name, "status": "complete", "evidence": [{"id": name}]}
        for name in names
    }
    output = {
        "status": "pass", "summary": "ok", "issues": [],
        "tool_receipts": [
            {"tool": name, "status": "complete", "evidence_ids": [name]}
            for name in names
        ],
    }
    return reports, output
