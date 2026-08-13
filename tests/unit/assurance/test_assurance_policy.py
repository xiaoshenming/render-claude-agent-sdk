import pytest

from manim_quality.assurance.policy import RawAgentAssessment, apply_assurance_policy


def test_policy_adjustment_is_versioned_hashed_and_revalidated() -> None:
    reports, output = _contract()

    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")

    assert adjusted.policy_version == "final-assurance-policy-v3"
    assert len(adjusted.policy_sha256) == 64
    assert adjusted.raw_sha256 == adjusted.adjusted_sha256


def test_policy_rejects_invalid_adjusted_contract() -> None:
    reports, output = _contract()
    output["tool_receipts"][0]["status"] = "risk"

    with pytest.raises(ValueError, match="receipt status"):
        apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")


def test_policy_removes_null_result_revision_issue_when_tool_reports_no_risk() -> None:
    reports, output = _contract()
    reports["inspect_consistency"]["evidence"] = [{
        "id": "CASE:consistency",
        "run_final_revision": "R2",
        "result_final_revision": None,
        "delivery_source_sha256": "a" * 64,
    }]
    output["tool_receipts"][-1]["evidence_ids"] = ["CASE:consistency"]
    output["status"] = "review"
    output["summary"] = "result.json 未记录最终修订号。"
    output["issues"] = [{
        "severity": "medium",
        "category": "metadata",
        "summary": "result_final_revision 为空，无法确认一致性。",
        "evidence_ids": ["CASE:consistency"],
    }]

    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")

    assert adjusted.output["status"] == "pass"
    assert adjusted.output["issues"] == []
    assert adjusted.change_reasons == ("unreported_consistency_issue_removed",)


def test_policy_keeps_consistency_issue_when_tool_reports_mismatch() -> None:
    reports, output = _contract()
    reports["inspect_consistency"].update({
        "status": "risk",
        "risk_codes": ["revision_identity_mismatch"],
        "evidence": [{
            "id": "CASE:consistency",
            "run_final_revision": "R2",
            "result_final_revision": "R1",
            "delivery_source_sha256": "a" * 64,
        }],
    })
    output["tool_receipts"][-1].update({
        "status": "risk",
        "evidence_ids": ["CASE:consistency"],
    })
    output["status"] = "review"
    output["issues"] = [{
        "severity": "medium",
        "category": "metadata",
        "summary": "最终修订号不一致。",
        "evidence_ids": ["CASE:consistency"],
    }]

    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")

    assert adjusted.output["issues"] == output["issues"]
    assert adjusted.change_reasons == ()


def test_detector_medium_is_warning_when_both_core_reviewers_pass() -> None:
    reports, output = _contract()
    output["status"] = "review"
    output["issues"] = [{
        "severity": "medium",
        "category": "layout",
        "summary": "detector candidate overlap",
        "evidence_ids": ["inspect_layout"],
    }]

    adjusted = apply_assurance_policy(
        RawAgentAssessment(output), reports, "CASE", reviewers=_passing_reviewers())

    assert adjusted.output["issues"][0]["severity"] == "warning"
    assert adjusted.change_reasons == (
        "unconfirmed_detector_medium_downgraded",
    )


def test_reviewer_needs_repair_keeps_medium() -> None:
    reports, output = _contract()
    output["status"] = "review"
    output["issues"] = [{
        "severity": "medium",
        "category": "layout",
        "summary": "visible overlap",
        "evidence_ids": ["inspect_risk_frames"],
    }]
    reviewers = list(_passing_reviewers())
    reviewers[1]["payload"]["decision"] = "needs_repair"

    adjusted = apply_assurance_policy(
        RawAgentAssessment(output), reports, "CASE", reviewers=tuple(reviewers))

    assert adjusted.output["issues"][0]["severity"] == "medium"
    assert adjusted.change_reasons == ()


def test_risk_frame_confirmation_keeps_medium_when_reviewers_pass() -> None:
    reports, output = _contract()
    reports["inspect_risk_frames"]["evidence"] = [{"id": "CASE:risk-frames"}]
    next(
        row for row in output["tool_receipts"]
        if row["tool"] == "inspect_risk_frames"
    )["evidence_ids"] = ["CASE:risk-frames"]
    output["status"] = "review"
    output["issues"] = [{
        "severity": "medium",
        "category": "layout",
        "summary": "visible overlap",
        "evidence_ids": ["CASE:risk-frames"],
    }]

    adjusted = apply_assurance_policy(
        RawAgentAssessment(output), reports, "CASE", reviewers=_passing_reviewers())

    assert adjusted.output["issues"][0]["severity"] == "medium"
    assert adjusted.change_reasons == ()


def _passing_reviewers():
    return tuple({
        "agent_type": name,
        "is_error": False,
        "payload": {"decision": "pass"},
    } for name in (
        "math_geometry_reviewer", "animation_lifecycle_reviewer",
    ))


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
