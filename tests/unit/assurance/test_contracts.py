import pytest

from manim_quality.assurance.contracts import validate_assurance_output
from manim_quality.contracts._json_values import freeze_json_object


def test_output_requires_every_tool_receipt() -> None:
    value = {
        "status": "pass",
        "summary": "发现最终产物风险",
        "tool_receipts": [
            {"tool": name, "status": "complete", "evidence_ids": ["e-1"]}
            for name in (
                "inspect_artifact",
                "inspect_execution",
                "inspect_code_review",
                "inspect_layout",
                "inspect_risk_frames",
                "inspect_tts",
                "inspect_consistency",
            )
        ],
        "issues": [],
    }

    validate_assurance_output(value)
    validate_assurance_output(freeze_json_object(value, "output"))


def test_pass_rejects_missing_or_risky_evidence() -> None:
    value = {
        "status": "pass",
        "summary": "错误地通过",
        "tool_receipts": [],
        "issues": [{"severity": "high", "category": "layout"}],
    }

    with pytest.raises(ValueError, match="required tool"):
        validate_assurance_output(value)


def test_output_receipts_must_match_observed_reports() -> None:
    value = valid_output()
    reports = {
        row["tool"]: {
            "status": "complete",
            "evidence": [{"id": f"{row['tool']}:actual"}],
        }
        for row in value["tool_receipts"]
    }

    with pytest.raises(ValueError, match="evidence does not match"):
        validate_assurance_output(value, expected_reports=reports)


def test_output_status_is_derived_from_tool_evidence() -> None:
    value = valid_output()
    value["tool_receipts"][0]["status"] = "risk"
    value["status"] = "pass"

    with pytest.raises(ValueError, match="pass cannot"):
        validate_assurance_output(value)


def test_output_rejects_unknown_issue_evidence() -> None:
    value = valid_output()
    value["status"] = "review"
    value["issues"] = [
        {
            "severity": "high",
            "category": "math",
            "summary": "unsupported",
            "evidence_ids": ["invented:evidence"],
        }
    ]
    reports = {
        row["tool"]: {
            "status": "complete",
            "evidence": [{"id": "e-1"}],
        }
        for row in value["tool_receipts"]
    }

    with pytest.raises(ValueError, match="unknown evidence"):
        validate_assurance_output(value, expected_reports=reports)


def valid_output() -> dict:
    return {
        "status": "pass",
        "summary": "所有工具证据完整",
        "tool_receipts": [
            {"tool": name, "status": "complete", "evidence_ids": ["e-1"]}
            for name in (
                "inspect_artifact",
                "inspect_execution",
                "inspect_code_review",
                "inspect_layout",
                "inspect_risk_frames",
                "inspect_tts",
                "inspect_consistency",
            )
        ],
        "issues": [],
    }
