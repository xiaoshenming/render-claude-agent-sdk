import json
from pathlib import Path

from manim_quality.feedback_loop.models import Candidate
from manim_quality.feedback_loop.subprocess_ports import (
    ProcessConfig,
    SubprocessCoder,
)


def test_coder_preserves_revision_and_all_runtime_paths(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    source = tmp_path / "R0.py"
    video = tmp_path / "R0.mp4"
    source.write_text("class Solution: pass\n", encoding="utf-8")
    video.write_bytes(b"old-video")
    runtime_paths = (tmp_path / "runtime-a", tmp_path / "runtime-b")
    captured = []

    def fake_run(argv, log_path, cwd):
        del log_path, cwd
        captured.extend(argv)
        output = tmp_path / "run" / "coder-1" / "output"
        case = output / "case-output"
        proposed = case / "output" / "proposed_candidate.py"
        proposed.parent.mkdir(parents=True)
        proposed.write_text("class Solution: fixed = True\n", encoding="utf-8")
        rendered = case / "rendered.mp4"
        rendered.write_bytes(b"new-video")
        (output / "batch_summary.json").write_text(
            json.dumps({"results": [{
                "status": "PROPOSED",
                "output": str(case),
                "decision": {
                    "final_revision_id": "R5",
                    "validation": {
                        "passed": True,
                        "details": {"video_path": str(rendered)},
                    },
                },
            }]}),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        "manim_quality.feedback_loop.subprocess_ports.run_command", fake_run
    )
    config = ProcessConfig(
        repo=repo,
        root=tmp_path / "run",
        case_id="case-1",
        question="question",
        assets_dir=None,
        model="model",
        manim_python=Path("python"),
        runtime_python_paths=runtime_paths,
    )

    result = SubprocessCoder(config).repair(
        Candidate("R0", "source", "video", str(source), str(video)),
        (),
        1,
    )

    assert result.revision_id == "R5"
    values = [
        captured[index + 1]
        for index, value in enumerate(captured)
        if value == "--runtime-python-path"
    ]
    assert values == [str(path) for path in runtime_paths]
    assert config.max_turns == 24
    assert config.max_tool_calls == 40
