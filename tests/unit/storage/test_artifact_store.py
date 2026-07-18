from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from manim_quality.storage.artifacts import (
    ArtifactCorruption,
    ArtifactHashMismatch,
    ArtifactRef,
    ArtifactStore,
    InvalidArtifactReference,
    LocalArtifactStore,
)


def test_put_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)

    first = store.put(b"rendered bytes", media_type="video/mp4")
    second = store.put(b"rendered bytes", media_type="video/mp4")

    assert first == second
    assert isinstance(store, ArtifactStore)
    assert first.hash.startswith("sha256:")
    assert first.size == len(b"rendered bytes")
    assert first.media_type == "video/mp4"
    assert Path(first.uri.removeprefix("file:///")).name == first.hash[7:]
    assert store.get(first) == b"rendered bytes"


def test_artifact_ref_is_frozen(tmp_path: Path) -> None:
    artifact = LocalArtifactStore(tmp_path).put(b"value", media_type="text/plain")

    with pytest.raises(FrozenInstanceError):
        artifact.size = 0  # type: ignore[misc]


def test_expected_hash_is_strictly_verified(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    expected = f"sha256:{'a' * 64}"

    with pytest.raises(ArtifactHashMismatch, match="expected hash"):
        store.put(b"actual", media_type="text/plain", expected_hash=expected)

    with pytest.raises(ValueError, match="canonical SHA-256"):
        store.put(b"actual", media_type="text/plain", expected_hash="../escape")


def test_existing_corrupt_artifact_is_never_overwritten(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    artifact = store.put(b"trusted", media_type="application/octet-stream")
    path = Path(artifact.uri.removeprefix("file:///"))
    path.write_bytes(b"corrupt")

    with pytest.raises(ArtifactCorruption, match="content does not match"):
        store.put(b"trusted", media_type="application/octet-stream")

    assert path.read_bytes() == b"corrupt"


def test_get_rehashes_content_and_rejects_tampering(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path)
    artifact = store.put(b"trusted", media_type="application/octet-stream")
    Path(artifact.uri.removeprefix("file:///")).write_bytes(b"tampered")

    with pytest.raises(ArtifactCorruption, match="content does not match"):
        store.get(artifact)


def test_get_rejects_caller_supplied_uri(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path / "store")
    artifact = store.put(b"trusted", media_type="text/plain")
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"trusted")
    forged = ArtifactRef(
        uri=outside.resolve().as_uri(),
        hash=artifact.hash,
        size=artifact.size,
        media_type=artifact.media_type,
    )

    with pytest.raises(InvalidArtifactReference, match="computed digest path"):
        store.get(forged)
