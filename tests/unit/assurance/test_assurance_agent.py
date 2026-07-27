import pytest

from manim_quality.assurance.agent import _validate_reviewers


def test_specialist_reviewers_must_both_complete() -> None:
    reviewers = (
        reviewer("math_geometry_reviewer"),
        reviewer("animation_lifecycle_reviewer"),
    )

    _validate_reviewers(reviewers)


def test_specialist_reviewer_error_is_rejected() -> None:
    reviewers = (
        reviewer("math_geometry_reviewer"),
        reviewer("animation_lifecycle_reviewer", is_error=True),
    )

    with pytest.raises(RuntimeError, match="exactly two"):
        _validate_reviewers(reviewers)


def reviewer(name: str, *, is_error: bool = False) -> dict:
    return {
        "agent_type": name,
        "is_error": is_error,
        "payload": {"decision": "pass"},
    }
