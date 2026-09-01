import pytest

from manim_quality.assurance.agent import (
    _validate_reviewers,
)
from manim_quality.assurance.policy import (
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
    }

    _normalize_derived_parameters(output, reports, "CASE")

    assert output["status"] == "review"
    issue = output["issues"][0]
    assert issue["severity"] == "high"
    assert "-0.18" in issue["summary"]
    assert "-0.8" in issue["summary"]
    assert issue["evidence_ids"] == ["CASE:final-source"]


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
    }

    _normalize_derived_parameters(output, reports, "CASE")

    issue = output["issues"][0]
    assert issue["severity"] == "high"
    assert issue["evidence_ids"] == [
        "reviewer:math_geometry_reviewer",
        "CASE:final-source",
    ]


def reviewer(name: str, *, is_error: bool = False) -> dict:
    return {
        "agent_type": name,
        "is_error": is_error,
        "payload": {"decision": "pass"},
    }
