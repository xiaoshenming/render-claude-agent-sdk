from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from manim_quality.contracts import QualitySubmission


def _submission() -> QualitySubmission:
    return QualitySubmission(
        job_id="job-123",
        tenant_id="tenant-456",
        candidate_code_ref="artifact://candidate.py",
        problem_text="Find the value of x.",
        planning={
            "scenes": [{"id": "scene-1", "goals": ["introduce", "solve"]}],
            "metadata": {"grade": 7, "reviewed": False},
        },
        expected_answer="x = 4",
        render_manifest_ref="artifact://render-manifest.json",
        asset_manifest_ref="artifact://asset-manifest.json",
        callback_url="https://example.test/quality-callback",
        idempotency_key="quality:job-123:1",
    )


def test_submission_is_frozen_slotted_and_roundtrips_stably() -> None:
    submission = _submission()

    assert is_dataclass(submission)
    assert submission.__dataclass_params__.frozen is True
    assert not hasattr(submission, "__dict__")
    assert "schema_version" in {item.name for item in fields(submission)}
    with pytest.raises(FrozenInstanceError):
        submission.job_id = "changed"  # type: ignore[misc]

    payload = submission.to_dict()
    restored = QualitySubmission.from_dict(payload)

    assert restored == submission
    assert restored.to_dict() == payload
    assert json.dumps(restored.to_dict(), separators=(",", ":")) == json.dumps(
        payload, separators=(",", ":")
    )


def test_submission_deep_freezes_planning_and_returns_detached_json() -> None:
    planning = {"scene": {"steps": ["first", {"label": "second"}]}}
    submission = QualitySubmission(
        job_id="job-123",
        tenant_id="tenant-456",
        candidate_code_ref="artifact://candidate.py",
        problem_text="Find x.",
        planning=planning,
        expected_answer=None,
        render_manifest_ref=None,
        asset_manifest_ref=None,
        callback_url=None,
        idempotency_key="quality:job-123:1",
    )

    planning["scene"]["steps"][0] = "mutated"  # type: ignore[index]
    planning["scene"]["steps"][1]["label"] = "mutated"  # type: ignore[index]
    serialized = submission.to_dict()

    assert serialized["planning"]["scene"]["steps"] == [
        "first",
        {"label": "second"},
    ]
    serialized["planning"]["scene"]["steps"][0] = "detached"  # type: ignore[index]
    assert submission.to_dict()["planning"]["scene"]["steps"][0] == "first"


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda payload: payload.pop("schema_version"), "schema_version"),
        (
            lambda payload: payload.__setitem__("schema_version", "unsupported"),
            "schema_version",
        ),
        (lambda payload: payload.__setitem__("extra", True), "unknown field"),
    ],
)
def test_submission_from_dict_rejects_invalid_contract_shape(
    change: object,
    match: str,
) -> None:
    payload = _submission().to_dict()
    change(payload)  # type: ignore[operator]

    with pytest.raises((TypeError, ValueError), match=match):
        QualitySubmission.from_dict(payload)


@pytest.mark.parametrize(
    "field_name",
    [
        "job_id",
        "tenant_id",
        "candidate_code_ref",
        "problem_text",
        "idempotency_key",
    ],
)
def test_submission_rejects_blank_required_identifiers(field_name: str) -> None:
    payload = _submission().to_dict()
    payload[field_name] = "   "

    with pytest.raises(ValueError, match=field_name):
        QualitySubmission.from_dict(payload)


@pytest.mark.parametrize(
    "field_name",
    ["render_manifest_ref", "asset_manifest_ref", "callback_url"],
)
def test_submission_rejects_blank_optional_references(field_name: str) -> None:
    payload = _submission().to_dict()
    payload[field_name] = ""

    with pytest.raises(ValueError, match=field_name):
        QualitySubmission.from_dict(payload)


def test_submission_rejects_non_json_planning_values() -> None:
    with pytest.raises(TypeError, match="planning"):
        QualitySubmission(
            job_id="job-123",
            tenant_id="tenant-456",
            candidate_code_ref="artifact://candidate.py",
            problem_text="Find x.",
            planning={"invalid": {1, 2}},
            expected_answer=None,
            render_manifest_ref=None,
            asset_manifest_ref=None,
            callback_url=None,
            idempotency_key="quality:job-123:1",
        )


@pytest.mark.parametrize(
    "planning",
    [
        {"not_finite": float("nan")},
        {1: "non-string key"},
    ],
)
def test_submission_rejects_values_that_strict_json_cannot_encode(
    planning: dict[object, object],
) -> None:
    payload = _submission().to_dict()
    payload["planning"] = planning

    with pytest.raises((TypeError, ValueError), match="planning"):
        QualitySubmission.from_dict(payload)


def test_submission_roundtrips_finite_json_numbers() -> None:
    payload = _submission().to_dict()
    payload["planning"] = {"duration_seconds": 1.5}

    assert QualitySubmission.from_dict(payload).to_dict()["planning"] == {
        "duration_seconds": 1.5
    }


def test_submission_requires_planning_to_be_a_json_object() -> None:
    payload = _submission().to_dict()
    payload["planning"] = []

    with pytest.raises(TypeError, match="planning"):
        QualitySubmission.from_dict(payload)


@pytest.mark.parametrize("payload", [[], {1: "invalid key"}])
def test_submission_from_dict_requires_a_json_object_with_string_keys(
    payload: object,
) -> None:
    with pytest.raises(TypeError):
        QualitySubmission.from_dict(payload)


def test_submission_rejects_non_string_optional_text() -> None:
    payload = _submission().to_dict()
    payload["expected_answer"] = 4

    with pytest.raises(TypeError, match="expected_answer"):
        QualitySubmission.from_dict(payload)
