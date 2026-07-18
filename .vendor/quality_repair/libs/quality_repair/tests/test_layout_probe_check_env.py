import os

from tools.quality_repair_checkers.layout_probe_check import (
    DEFAULT_LAYOUT_PROBE_IMAGE,
    _ensure_probe_env,
)


def test_layout_probe_check_sets_project_default_image(monkeypatch) -> None:
    monkeypatch.delenv("VIDEO_QUALITY_REPAIR_LAB_MANIM_IMAGE", raising=False)

    _ensure_probe_env()

    assert DEFAULT_LAYOUT_PROBE_IMAGE == "docker-manim-worker-1:latest"
    assert "docker-manim-worker-1:latest" == os.environ["VIDEO_QUALITY_REPAIR_LAB_MANIM_IMAGE"]
