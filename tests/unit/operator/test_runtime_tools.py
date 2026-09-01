import json
from pathlib import Path

import pytest

from manim_quality.operator.models import CandidateAttempt
from manim_quality.operator.runtime_tools.issues import compact_layout_report
from manim_quality.operator.runtime_tools.workspace import RevisionWorkspace


def _revision(code: str = "class Solution:\n    pass\n") -> CandidateAttempt:
    return CandidateAttempt(
        revision_id="R1",
        parent_revision_id="R0",
        scope=None,
        code=code,
        code_hash="sha256:" + "a" * 64,
        patch_hash=None,
        finding_ids=(),
    )


def test_revision_workspace_materializes_identity_and_code(tmp_path: Path) -> None:
    revision_dir, candidate = RevisionWorkspace(tmp_path).materialize(_revision())

    assert candidate.read_text(encoding="utf-8") == _revision().code
    identity = json.loads(
        (revision_dir / "revision.json").read_text(encoding="utf-8")
    )
    assert identity["revision_id"] == "R1"
    assert identity["code_hash"] == _revision().code_hash


def test_compact_layout_report_returns_only_bounded_issue_facts() -> None:
    issues = [
        {
            "category": "text_formula_overlap",
            "ratio_of_smaller": 0.4,
            "x_overlap": 0.2,
            "y_overlap": 0.3,
            "step": index,
            "a_raw": {
                "path": f"mobjects.{index}",
                "class": "Text",
                "kind": "text",
                "text": "proof",
                "bbox": {"left": 0, "right": 1},
                "points": [[0, 0]] * 100,
            },
            "b_raw": {
                "path": f"mobjects.{index + 1}",
                "class": "MathTex",
                "kind": "formula",
                "text": "x=1",
                "bbox": {"left": 0.8, "right": 2},
            },
        }
        for index in range(25)
    ]

    result = compact_layout_report({"issues": issues}, max_issues=20)

    assert result["blocking_count"] == 25
    assert result["returned_issue_count"] == 20
    assert result["truncated"] is True
    assert "points" not in json.dumps(result)
    assert result["issues"][0]["objects"][0]["path"] == "mobjects.0"


def test_bbox_probe_reuses_combined_real_render_evidence(tmp_path: Path) -> None:
    from manim_quality.operator.runtime_tools.probe import _combined_result

    revision = tmp_path / "R1"
    revision.mkdir()
    payload = {
        "capture_mode": "combined_real_render",
        "scene": "Solution",
        "error_count": 0,
        "snapshot_count": 2,
        "top_overlaps": [],
        "top_bounds_violations": [],
    }
    geometry = {
        "version": 1,
        "capture_mode": "combined_real_render",
        "captures": [],
    }
    (revision / "combined_bbox_probe.json").write_text(
        json.dumps(payload), encoding="utf-8")
    (revision / "combined_geometry_sidecar.json").write_text(
        json.dumps(geometry), encoding="utf-8")

    result = _combined_result(revision, revision / "bbox_probe.json")

    assert result is not None and result.ok is True
    assert result.payload["capture_mode"] == "combined_real_render"
    assert (revision / "geometry_sidecar.json").is_file()


def test_verification_receipt_reuses_video_and_bbox_across_sessions(
    tmp_path: Path,
) -> None:
    from manim_quality.operator.runtime_tools.models import RenderResult
    from manim_quality.operator.runtime_tools.verification_renderer import (
        VerificationRenderer,
    )

    class Renderer:
        calls = 0

        def render(self, revision_dir, candidate):
            self.calls += 1
            revision_dir.mkdir(parents=True, exist_ok=True)
            video = revision_dir / "verified_video.mp4"
            video.write_bytes(b"video")
            for name in (
                "combined_bbox_probe.json",
                "combined_geometry_sidecar.json",
            ):
                (revision_dir / name).write_text("{}", encoding="utf-8")
            return RenderResult(
                True, revision_dir, candidate, video, 3.0, None,
                elapsed_ms=100,
            )

    renderer = Renderer()
    code_hash = "sha256:" + "b" * 64
    first = VerificationRenderer(renderer, tmp_path / "cache")
    first.render(tmp_path / "session-1", tmp_path / "candidate.py", code_hash)
    second = VerificationRenderer(renderer, tmp_path / "cache")
    result = second.render(
        tmp_path / "session-2", tmp_path / "candidate.py", code_hash)

    assert renderer.calls == 1
    assert result.elapsed_ms == 0
    assert result.video_path.read_bytes() == b"video"
    assert (tmp_path / "session-2/combined_bbox_probe.json").is_file()


def test_detached_render_groups_are_tracked_and_reapable(tmp_path) -> None:
    """A supervisor group-kill cannot reach detached render sessions, so
    live groups must be registered for explicit reaping."""
    import sys
    import time

    from manim_quality.operator.runtime_tools import process as process_module

    argv = [sys.executable, "-c", "import time; time.sleep(30)"]
    holder = {}

    def run_in_thread():
        try:
            process_module.run_to_artifacts(
                argv,
                cwd=tmp_path,
                timeout_seconds=25,
                stdout_path=tmp_path / "out.log",
                stderr_path=tmp_path / "err.log",
            )
        except Exception as error:
            holder["error"] = error

    import threading

    worker = threading.Thread(target=run_in_thread, daemon=True)
    worker.start()
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not process_module._ACTIVE_GROUPS:
        time.sleep(0.05)
    assert process_module._ACTIVE_GROUPS, "live render group must be registered"

    reaped = process_module.kill_active_process_groups()
    assert reaped == 1
    worker.join(timeout=10)
    assert not process_module._ACTIVE_GROUPS


def test_render_cache_flag_controls_manim_caching(tmp_path) -> None:
    from manim_quality.operator.runtime_tools.render import (
        ManimRenderer,
        _newest_video,
    )

    workspace = tmp_path / "ws"
    workspace.mkdir()
    interpreter = tmp_path / "python"
    interpreter.touch()

    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs.get("env_overrides")
        raise OSError("stop before real subprocess")

    import manim_quality.operator.runtime_tools.render as render_module

    original = render_module.run_to_artifacts
    render_module.run_to_artifacts = fake_run
    try:
        cold = ManimRenderer(
            source_workspace=workspace,
            python_executable=interpreter,
        )
        cold.render(tmp_path / "R1", tmp_path / "c.py")
        assert "--disable_caching" in captured["argv"]
        assert str(tmp_path / "R1" / "media") in captured["argv"]
        assert captured["env"]["MANIM_COMBINED_BBOX_PATH"].endswith(
            "R1/combined_bbox_probe.json")

        cached = ManimRenderer(
            source_workspace=workspace,
            python_executable=interpreter,
            cache_dir=tmp_path / "shared_cache",
        )
        cached.render(tmp_path / "R2", tmp_path / "c.py")
        assert "--disable_caching" not in captured["argv"]
        assert str(tmp_path / "shared_cache") in captured["argv"]
    finally:
        render_module.run_to_artifacts = original

    # final video selection must skip Manim's partial movie segments
    final_dir = tmp_path / "shared_cache" / "videos" / "c" / "480p15"
    partial = final_dir / "partial_movie_files" / "Solution"
    partial.mkdir(parents=True)
    (final_dir / "Solution.mp4").write_bytes(b"final")
    import time

    time.sleep(0.01)
    (partial / "seg01.mp4").write_bytes(b"segment-newer-mtime")
    chosen = _newest_video(tmp_path / "shared_cache")
    assert chosen is not None and chosen.name == "Solution.mp4"


@pytest.mark.parametrize("cache_enabled", [False, True])
def test_render_result_freezes_verified_video_with_or_without_cache(
    tmp_path, cache_enabled,
) -> None:
    from types import SimpleNamespace

    import manim_quality.operator.runtime_tools.render as render_module
    from manim_quality.operator.runtime_tools.render import ManimRenderer

    workspace, cache = tmp_path / "ws", tmp_path / "cache"
    workspace.mkdir()
    interpreter, candidate = tmp_path / "python", tmp_path / "candidate.py"
    interpreter.touch()
    candidate.write_text("class Solution: pass\n", encoding="utf-8")

    def fake_run(argv, **_kwargs):
        if "-m" in argv and "manim" in argv:
            media = Path(argv[argv.index("--media_dir") + 1])
            partial = media / "videos/480p15/partial_movie_files/Solution/a.mp4"
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_bytes(b"partial")
            video = media / "videos/480p15/Solution.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"video")
            return SimpleNamespace(
                returncode=0,
                stdout="Using cached data (hash)",
                stderr="Using cached\n    data (wrapped hash)",
            )
        return SimpleNamespace(
            returncode=0,
            stdout='{"format":{"duration":"2.0"}}',
            stderr="",
        )

    original = render_module.run_to_artifacts
    render_module.run_to_artifacts = fake_run
    try:
        result = ManimRenderer(
            source_workspace=workspace,
            python_executable=interpreter,
            cache_dir=cache if cache_enabled else None,
        ).render(tmp_path / "R1", candidate)
    finally:
        render_module.run_to_artifacts = original

    assert result.ok is True
    assert result.video_path == tmp_path / "R1" / "verified_video.mp4"
    assert result.video_path.read_bytes() == b"video"
    assert result.cache_hit_count == 2
    assert result.new_partial_count == 1
    assert result.elapsed_ms is not None
