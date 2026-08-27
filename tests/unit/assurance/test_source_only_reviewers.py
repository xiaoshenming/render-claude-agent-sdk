from pathlib import Path
from types import SimpleNamespace

from manim_quality.assurance import agent as agent_module


def test_source_only_assurance_still_runs_formal_reviewers(
    monkeypatch, tmp_path: Path,
) -> None:
    source = tmp_path / "candidate.py"
    source.write_text("class Solution: pass\n", encoding="utf-8")
    case = SimpleNamespace(
        source_path=source, question="题目", solution_steps="步骤",
        final_answer="B",
    )
    captured = {}

    def run_reviewers(runtime, **kwargs):
        captured.update(kwargs)
        return (({"agent_type": "math_geometry_reviewer"},), ("record",))

    monkeypatch.setattr(agent_module, "run_reviewers", run_reviewers)

    reviewers, records = agent_module._native_reviewers(
        object(), "gpt-5.6-sol", case, verification=None)

    assert reviewers == ({"agent_type": "math_geometry_reviewer"},)
    assert records == ("record",)
    assert captured["candidate_path"] == source
    assert captured["problem_text"] == "题目"
    assert captured["solution_steps"] == "步骤"
    assert captured["final_answer"] == "B"
