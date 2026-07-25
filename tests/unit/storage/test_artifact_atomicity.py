from pathlib import Path

import pytest

import manim_quality.storage.artifacts as artifacts_module
from manim_quality.storage.artifacts import LocalArtifactStore


def test_publish_failure_leaves_no_artifact_or_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = LocalArtifactStore(tmp_path)

    def fail_publish(source: str, target: str) -> None:
        raise OSError("injected publish failure")

    monkeypatch.setattr(artifacts_module.os, "link", fail_publish)

    with pytest.raises(OSError, match="injected publish failure"):
        store.put(b"never published", media_type="application/octet-stream")

    assert [path for path in tmp_path.rglob("*") if path.is_file()] == []
