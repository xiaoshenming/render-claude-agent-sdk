import pytest

from manim_quality.contracts import QualityState
from manim_quality.revisions.fingerprint import (
    PythonSyntaxError,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_bytes,
    sha256_text,
)
from manim_quality.revisions.store import QualityJobSnapshot, require_expected_version


def snapshot(**changes: object) -> QualityJobSnapshot:
    values: dict[str, object] = {
        "job_id": "job-1",
        "version": 0,
        "state": QualityState.BASELINE_READY,
        "render_baseline_revision_id": "rev-1",
        "logic_certified_revision_id": None,
        "layout_certified_revision_id": None,
        "delivery_revision_id": None,
    }
    values.update(changes)
    return QualityJobSnapshot(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"job_id": ""},
        {"job_id": 1},
        {"version": -1},
        {"version": True},
        {"state": "BASELINE_READY"},
        {"render_baseline_revision_id": ""},
        {"delivery_revision_id": ""},
        {"logic_certified_evidence_hash": "not-a-hash"},
    ],
)
def test_job_snapshot_rejects_invalid_fields(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        snapshot(**changes)


@pytest.mark.parametrize("value", [-1, True, "0"])
def test_expected_version_must_be_non_negative_integer(value: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        require_expected_version(value)


@pytest.mark.parametrize(
    ("function", "value"),
    [(sha256_bytes, "bytes"), (sha256_text, b"text"), (semantic_fingerprint, 1)],
)
def test_fingerprint_inputs_are_typed(function: object, value: object) -> None:
    with pytest.raises(TypeError):
        function(value)  # type: ignore[operator]


def test_scene_detection_supports_qualified_bases() -> None:
    assert list(scene_fingerprints("class Lesson(manim.Scene):\n    pass\n")) == [
        "Lesson"
    ]


def test_syntax_error_without_column_still_has_location() -> None:
    error = SyntaxError("bad source", ("lesson.py", 4, None, "bad"))

    assert "line 4" in str(PythonSyntaxError(error))
