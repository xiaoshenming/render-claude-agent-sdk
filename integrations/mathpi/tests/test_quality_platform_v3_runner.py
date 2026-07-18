from pathlib import Path
from types import SimpleNamespace

from app.quality_platform.v3_runner import run_v3_existing_code


def test_selects_v3_final_candidate(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "v3"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/run_existing_code_e2e.py").write_text("", encoding="utf-8")
    (root / "bin").mkdir()
    (root / "bin/manim-python").write_text("", encoding="utf-8")
    monkeypatch.setenv("MANIM_QUALITY_V3_ROOT", str(root))

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        run_dir = Path(command[command.index("--output") + 1])
        run_dir.mkdir(parents=True)
        (run_dir / "candidate_final.py").write_text("fixed = True\n", encoding="utf-8")
        (run_dir / "video_final.mp4").write_bytes(b"fixed-video")
        (run_dir / "result.json").write_text(
            '{"status":"deliver","logic":{"status":"candidate_ready"},'
            '"layout":{"status":"clean"}}',
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.quality_platform.v3_runner.subprocess.run", fake_run)
    result = run_v3_existing_code(
        job_id="job-1",
        candidate_code="fixed = False\n",
        problem_text="problem",
        expected_solution="solution",
        output_dir=tmp_path / "artifacts",
    )

    assert result.status == "deliver"
    assert result.selected_code == "fixed = True\n"
    assert result.final_video_path.read_bytes() == b"fixed-video"
    assert result.fail_open_used is False
    command = captured["command"]
    assert command[command.index("--layout-token-budget") + 1] == "180000"


def test_v3_failure_preserves_renderable_input(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MANIM_QUALITY_V3_ROOT", str(tmp_path / "missing"))
    result = run_v3_existing_code(
        job_id="job-2",
        candidate_code="playable = True\n",
        problem_text="problem",
        expected_solution="solution",
        output_dir=tmp_path / "artifacts",
    )

    assert result.status == "fail_open"
    assert result.selected_code == "playable = True\n"
    assert result.fail_open_used is True


def test_layout_budget_override_is_bounded(monkeypatch) -> None:
    from app.quality_platform.v3_runner import _layout_token_budget

    monkeypatch.setenv("MANIM_QUALITY_LAYOUT_TOKEN_BUDGET", "999999")
    assert _layout_token_budget() == 300_000
    monkeypatch.setenv("MANIM_QUALITY_LAYOUT_TOKEN_BUDGET", "invalid")
    assert _layout_token_budget() == 180_000
