import pytest

from manim_quality.assurance.detector_policy import normalize_detector_issues
from manim_quality.assurance.policy import RawAgentAssessment, apply_assurance_policy


def test_policy_adjustment_is_versioned_hashed_and_revalidated() -> None:
    reports, output = _contract()

    adjusted = apply_assurance_policy(RawAgentAssessment(output), reports, "CASE")

    assert adjusted.policy_version == "final-assurance-policy-v4"
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


@pytest.mark.parametrize("severity", ["medium", "high"])
def test_freeze_only_telemetry_is_warning_when_reviewers_pass(severity) -> None:
    reports, output = _contract()
    reports["inspect_risk_frames"]["evidence"] = [{
        "id": "CASE:risk-frames",
        "windows": {"black": [], "freeze": [{"start": 1.0, "end": 9.0}]},
    }]
    _risk_frame_receipt(output)["evidence_ids"] = ["CASE:risk-frames"]
    output["status"] = "review"
    output["issues"] = [{
        "severity": severity,
        "category": "temporal_freeze",
        "summary": "冻结窗口可能是正常静态讲解停留",
        "evidence_ids": ["CASE:risk-frames"],
    }]

    adjusted = apply_assurance_policy(
        RawAgentAssessment(output), reports, "CASE", reviewers=_passing_reviewers())

    assert adjusted.output["issues"][0]["severity"] == "warning"
    assert adjusted.change_reasons == (
        "unconfirmed_freeze_telemetry_downgraded",
    )


def test_black_window_keeps_freeze_issue_actionable() -> None:
    reports, output = _contract()
    reports["inspect_risk_frames"].update({
        "status": "risk",
        "risk_codes": ["black_frame_window"],
        "evidence": [{
            "id": "CASE:risk-frames",
            "windows": {
                "black": [{"start": 1.0, "end": 9.0}],
                "freeze": [{"start": 1.0, "end": 9.0}],
            },
        }],
    })
    _risk_frame_receipt(output).update({
        "status": "risk", "evidence_ids": ["CASE:risk-frames"],
    })
    output["status"] = "review"
    output["issues"] = [{
        "severity": "high",
        "category": "temporal_freeze",
        "summary": "黑屏伴随冻结",
        "evidence_ids": ["CASE:risk-frames"],
    }]

    adjusted = apply_assurance_policy(
        RawAgentAssessment(output), reports, "CASE", reviewers=_passing_reviewers())

    assert adjusted.output["issues"][0]["severity"] == "high"
    assert adjusted.change_reasons == ()


def test_detector_policy_handles_non_actionable_edge_shapes() -> None:
    reviewers = _passing_reviewers()
    assert normalize_detector_issues({}, {}, reviewers) == ()
    output = {"issues": [None, {
        "severity": "medium",
        "category": "temporal_freeze",
        "summary": "冻结窗口",
        "evidence_ids": ["reviewer:animation_lifecycle_reviewer"],
    }]}
    assert normalize_detector_issues(output, {}, reviewers) == ()
    issue = {
        "severity": "high",
        "category": "temporal_freeze",
        "summary": "冻结窗口",
        "evidence_ids": ["CASE:risk-frames"],
    }
    report = {
        "inspect_risk_frames": {
            "status": "complete", "risk_codes": ["black_frame_window"],
            "evidence": [{"windows": {"black": [], "freeze": [{}]}}],
        },
    }
    assert normalize_detector_issues(
        {"issues": [issue]}, report, reviewers) == ()
    report["inspect_risk_frames"].update({
        "risk_codes": [], "evidence": [{"windows": "unreported"}],
    })
    assert normalize_detector_issues(
        {"issues": [issue]}, report, reviewers) == ()


def _passing_reviewers():
    return tuple({
        "agent_type": name,
        "is_error": False,
        "payload": {"decision": "pass"},
    } for name in (
        "math_geometry_reviewer", "animation_lifecycle_reviewer",
    ))


def _risk_frame_receipt(output):
    return next(
        row for row in output["tool_receipts"]
        if row["tool"] == "inspect_risk_frames"
    )


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
