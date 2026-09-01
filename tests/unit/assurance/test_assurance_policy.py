import pytest

from manim_quality.assurance.policy import RawAgentAssessment, apply_assurance_policy


def test_policy_adjustment_is_versioned_hashed_and_revalidated() -> None:
    reports, output = _contract()
    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")
    assert adjusted.policy_version == "final-assurance-policy-v5"
    assert len(adjusted.policy_sha256) == 64
    assert adjusted.raw_sha256 == adjusted.adjusted_sha256


def test_policy_rejects_invalid_adjusted_contract() -> None:
    reports, output = _contract()
    output["tool_receipts"][0]["status"] = "risk"
    with pytest.raises(ValueError, match="receipt status"):
        apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")


def test_verified_layout_risk_is_promoted_to_medium_issue() -> None:
    reports, output = _layout_risk_contract()
    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")
    assert adjusted.output["issues"] == [{
        "severity": "medium",
        "category": "verified_layout_risk",
        "summary": "最终源码绑定的确定性BBox布局验证仍有blocking问题，必须返回Coder修复并重新验证。",
        "evidence_ids": ["CASE:quality-layout"],
    }]
    assert adjusted.change_reasons == ("verified_layout_risk_promoted",)


def test_existing_layout_issue_keeps_at_least_medium() -> None:
    reports, output = _layout_risk_contract()
    output["issues"] = [{
        "severity": "warning", "category": "layout",
        "summary": "detector overlap",
        "evidence_ids": ["CASE:quality-layout"],
    }]
    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")
    assert adjusted.output["issues"][0]["severity"] == "medium"


def test_policy_removes_null_result_revision_issue_when_tool_reports_no_risk() -> None:
    reports, output = _contract()
    reports["inspect_consistency"]["evidence"] = [{
        "id": "CASE:consistency", "run_final_revision": "R2",
        "result_final_revision": None, "delivery_source_sha256": "a" * 64,
    }]
    output["tool_receipts"][-1]["evidence_ids"] = ["CASE:consistency"]
    output.update(status="review", summary="metadata", issues=[{
        "severity": "medium", "category": "metadata",
        "summary": "result_final_revision missing",
        "evidence_ids": ["CASE:consistency"],
    }])
    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")
    assert adjusted.output["status"] == "pass"
    assert adjusted.output["issues"] == []
    assert adjusted.change_reasons == ("unreported_consistency_issue_removed",)


def _layout_risk_contract():
    reports, output = _contract()
    reports["inspect_layout"] = {
        "tool": "inspect_layout", "status": "risk",
        "risk_codes": ["blocking_layout_finding"],
        "evidence": [{"id": "CASE:quality-layout"}],
    }
    next(
        row for row in output["tool_receipts"] if row["tool"] == "inspect_layout"
    ).update(status="risk", evidence_ids=["CASE:quality-layout"])
    output.update(status="review", summary="layout review")
    return reports, output


def _contract():
    names = (
        "inspect_artifact", "inspect_execution", "inspect_code_review",
        "inspect_layout", "inspect_tts", "inspect_consistency",
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
