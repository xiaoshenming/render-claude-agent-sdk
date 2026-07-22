import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from evals.workbench_e2e import layout_stage, logic_stage, rendering
from scripts import run_existing_code_e2e as target


@dataclass
class LogicResult:
    status: str
    decision: str
    candidate_path: Path
    error: str = ""


@dataclass
class LayoutResult:
    status: str
    candidate_path: Path
    requires_render_recheck: bool = False
    error: str = ""


@dataclass
class RenderResult:
    succeeded: bool
    video_path: Path
    error: str = ""


def test_logic_rejection_still_runs_layout_and_delivers_warning(tmp_path, monkeypatch):
    code = tmp_path / "source.py"
    problem = tmp_path / "problem.txt"
    expected = tmp_path / "expected.txt"
    probe = tmp_path / "probe.py"
    vendor = tmp_path / "vendor"
    output = tmp_path / "run"
    code.write_text("class MainScene: pass\n", encoding="utf-8")
    problem.write_text("problem", encoding="utf-8")
    expected.write_text("expected", encoding="utf-8")
    probe.write_text("PROBE_RUNNER_SOURCE = ''\n", encoding="utf-8")
    vendor.mkdir()
    calls = []

    class Renderer:
        def __init__(self, **_kwargs):
            pass

        def render(self, _candidate, render_dir):
            video = Path(render_dir) / "video.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"video")
            return RenderResult(True, video)

    def reject_logic(**kwargs):
        return LogicResult("rejected", "needs_repair", kwargs["candidate"])

    def run_layout(**kwargs):
        calls.append(kwargs["candidate"])
        return LayoutResult("clean", kwargs["candidate"])

    monkeypatch.setattr(rendering, "LocalManimRenderer", Renderer)
    monkeypatch.setattr(logic_stage, "run_logic_stage", reject_logic)
    monkeypatch.setattr(layout_stage, "run_layout_stage", run_layout)
    monkeypatch.setattr(target, "_api_key", lambda: "test-key")
    monkeypatch.setattr(target, "_arguments", lambda: SimpleNamespace(
        code=code,
        problem=problem,
        expected_solution=expected,
        output=output,
        manim_python=tmp_path / "python",
        job_id="job-1",
        base_url="http://example.test",
        model="test-model",
        probe_source=probe,
        vendor_root=vendor,
        layout_token_budget=100,
        allow_vendor_clean_fallback=True,
    ))

    assert target.main() == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert calls == [output / "candidate_input.py"]
    assert result["status"] == "deliver_with_warning"
    assert result["logic"]["status"] == "rejected"
    assert result["layout"]["status"] == "clean"
