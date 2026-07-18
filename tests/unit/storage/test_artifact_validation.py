from pathlib import Path

import pytest

from manim_quality.storage.artifacts import (
    ArtifactCorruption,
    ArtifactRef,
    LocalArtifactStore,
)

HASH = f"sha256:{'a' * 64}"


@pytest.mark.parametrize(
    "changes",
    [
        {"uri": ""},
        {"hash": "sha256:bad"},
        {"size": -1},
        {"size": True},
        {"media_type": " "},
    ],
)
def test_artifact_ref_rejects_invalid_fields(changes: dict[str, object]) -> None:
    values: dict[str, object] = {
        "uri": "file:///artifact",
        "hash": HASH,
        "size": 1,
        "media_type": "text/plain",
    }
    values.update(changes)

    with pytest.raises(ValueError):
        ArtifactRef(**values)  # type: ignore[arg-type]


def test_invalid_media_type_is_rejected_before_writing(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    with pytest.raises(ValueError, match="media_type"):
        store.put(b"orphan", media_type=" ")

    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []


def test_get_rejects_wrong_type_and_missing_file(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    with pytest.raises(TypeError, match="ArtifactRef"):
        store.get(object())  # type: ignore[arg-type]

    artifact = store.put(b"temporary", media_type="text/plain")
    Path(artifact.uri.removeprefix("file:///")).unlink()
    with pytest.raises(ArtifactCorruption, match="cannot be read"):
        store.get(artifact)
