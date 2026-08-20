import pytest

from manim_quality.assurance.agent import (
    _validate_reviewers,
)
from manim_quality.assurance.policy import (
    _normalize_anchor_drift,
    _normalize_derived_parameters,
)


def test_all_three_specialist_reviewers_can_complete() -> None:
    reviewers = (
        reviewer("math_geometry_reviewer"),
        reviewer("animation_lifecycle_reviewer"),
        reviewer("visual_layout_reviewer"),
    )

    _validate_reviewers(reviewers)


def test_specialist_reviewer_error_is_rejected() -> None:
    reviewers = (
        reviewer("math_geometry_reviewer"),
        reviewer("animation_lifecycle_reviewer", is_error=True),
        reviewer("visual_layout_reviewer"),
    )

    with pytest.raises(RuntimeError, match="both core"):
        _validate_reviewers(reviewers)


def test_visual_reviewer_failure_is_evidence_only() -> None:
    reviewers = (
        reviewer("math_geometry_reviewer"),
        reviewer("animation_lifecycle_reviewer"),
        reviewer("visual_layout_reviewer", is_error=True),
    )

    _validate_reviewers(reviewers)


def test_figure_fidelity_reviewer_is_optional_evidence() -> None:
    reviewers = (
        reviewer("math_geometry_reviewer"),
        reviewer("animation_lifecycle_reviewer"),
        reviewer("visual_layout_reviewer"),
        reviewer("figure_fidelity_reviewer"),
    )

    _validate_reviewers(reviewers)


def test_derived_parameter_evidence_becomes_coder_issue() -> None:
    output = {"status": "review", "summary": "review", "issues": []}
    reports = {
        "inspect_code_review": {
            "evidence": [
                {
                    "derived_parameter_mismatches": [
                        {
                            "line": 1955,
                            "helper": "make_mini_fig",
                            "parameter": "kb_val",
                            "expression": "k_val * b_val",
                            "expected": -0.18,
                            "actual": -0.8,
                        }
                    ]
                }
            ]
        },
        "inspect_risk_frames": {"evidence": [{"id": "CASE:risk-frames"}]},
    }

    _normalize_derived_parameters(output, reports, "CASE")

    assert output["status"] == "review"
    issue = output["issues"][0]
    assert issue["severity"] == "high"
    assert "-0.18" in issue["summary"]
    assert "-0.8" in issue["summary"]
    assert issue["evidence_ids"] == ["CASE:final-source", "CASE:risk-frames"]


def test_existing_derived_parameter_issue_is_upgraded() -> None:
    output = {
        "status": "review",
        "summary": "review",
        "issues": [
            {
                "severity": "medium",
                "category": "mathematics",
                "summary": "expected -0.18, actual -0.8",
                "evidence_ids": ["reviewer:math_geometry_reviewer"],
            }
        ],
    }
    reports = {
        "inspect_code_review": {
            "evidence": [
                {
                    "derived_parameter_mismatches": [
                        {
                            "line": 1955,
                            "helper": "make_mini_fig",
                            "parameter": "kb_val",
                            "expression": "k_val * b_val",
                            "expected": -0.18,
                            "actual": -0.8,
                        }
                    ]
                }
            ]
        },
        "inspect_risk_frames": {"evidence": [{"id": "CASE:risk-frames"}]},
    }

    _normalize_derived_parameters(output, reports, "CASE")

    issue = output["issues"][0]
    assert issue["severity"] == "high"
    assert issue["evidence_ids"] == [
        "reviewer:math_geometry_reviewer",
        "CASE:final-source",
        "CASE:risk-frames",
    ]


def test_confirmed_anchor_drift_is_always_high() -> None:
    output = {
        "issues": [
            {
                "severity": "medium",
                "summary": "旧坐标生成的高亮已与目标边脱离并出现漂移",
                "evidence_ids": ["CASE:risk-frames"],
            },
            {
                "severity": "medium",
                "summary": "源码可能存在旧坐标风险",
                "evidence_ids": ["CASE:final-source"],
            },
        ]
    }

    _normalize_anchor_drift(output)

    assert output["issues"][0]["severity"] == "high"
    assert output["issues"][1]["severity"] == "medium"


def reviewer(name: str, *, is_error: bool = False) -> dict:
    return {
        "agent_type": name,
        "is_error": is_error,
        "payload": {"decision": "pass"},
    }
