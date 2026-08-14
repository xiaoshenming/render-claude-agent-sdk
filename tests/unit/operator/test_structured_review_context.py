from manim_quality.operator.agent import _review_context
from manim_quality.operator.session import QualitySession

CODE = (
    "class BaseConfigScene:\n    pass\n\n"
    "class Solution(BaseConfigScene):\n"
    "    def construct(self):\n"
    "        pass\n"
)


def test_parent_coder_receives_separate_truth_and_feedback(monkeypatch, tmp_path):
    (tmp_path / "main.py").write_text(CODE, encoding="utf-8")
    observed = {}

    def fake_reviewers(_runtime, **kwargs):
        observed.update(kwargs)
        return (({"agent_type": "math_geometry_reviewer"},), ())

    monkeypatch.setattr(
        "manim_quality.operator.agent.run_reviewers", fake_reviewers
    )
    session = QualitySession(
        problem_text="求证 AB=AC",
        solution_steps="先证全等，再得到 AB=AC",
        repair_feedback={"issue_id": "FA-1", "summary": "修正错线"},
        candidate_code=CODE,
    )

    _path, prompt, _results, _records = _review_context(
        object(), "model", tmp_path, session
    )

    assert observed["problem_text"] == "求证 AB=AC"
    assert observed["solution_steps"] == "先证全等，再得到 AB=AC"
    assert "先证全等，再得到 AB=AC" in prompt
    assert '"issue_id":"FA-1"' in prompt
    assert session.problem_text == "求证 AB=AC"
    assert session.solution_steps_hash.startswith("sha256:")
    assert session.repair_feedback_hash.startswith("sha256:")
