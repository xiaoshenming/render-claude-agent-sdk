from pathlib import Path
from types import SimpleNamespace

import pytest

from manim_quality.operator.figure_fidelity import (
    _decision,
    _validate_output,
    locate_confirmed_figure,
    run_figure_fidelity_reviewer,
)


def _sources(root: Path) -> tuple[Path, Path]:
    candidate = root / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        edge_ab = Line(LEFT, RIGHT)\n"
        "        self.add(edge_ab)\n",
        encoding="utf-8",
    )
    visual = root / "assets/visual"
    visual.mkdir(parents=True)
    figure = visual / "figure.py"
    figure.write_text(
        "from manim import *\n"
        "def build_figure():\n"
        "    return VGroup(Line(LEFT, RIGHT))\n",
        encoding="utf-8",
    )
    (visual / "figure-plan.json").write_text(
        '{"visual_role":"source_reconstruction"}', encoding="utf-8")
    return candidate, figure


class Runtime:
    def __init__(self, *, miss_figure_once: bool = False):
        self.requests = []
        self.miss_figure_once = miss_figure_once

    def run(self, request):
        self.requests.append(request)
        paths = list(request.readable_paths)
        if self.miss_figure_once and len(self.requests) == 1:
            paths = paths[:1]
        calls = tuple(SimpleNamespace(
            allowed=True, name="Read",
            input={"file_path": str(path), "offset": 1, "limit": 99},
        ) for path in paths)
        record = SimpleNamespace(
            tool_calls=calls, usage=SimpleNamespace(total_tokens=0),
            usage_complete=True, model="test-model", elapsed_ms=1, turns=1,
        )
        return SimpleNamespace(
            record=record,
            structured_output={
                "decision": "pass", "diagnosis": "对应关系完整", "issues": [],
                "coverage": {"figure": True, "candidate": True},
                "confidence": 0.95,
            },
        )


def test_code_only_reviewer_reads_both_sources(tmp_path) -> None:
    candidate, figure = _sources(tmp_path)
    runtime = Runtime()

    result, record = run_figure_fidelity_reviewer(
        runtime, candidate_path=candidate, figure_path=figure,
        problem_text="如图，判断 AB 的关系。", model="test-model",
    )

    assert result["agent_type"] == "figure_fidelity_reviewer"
    assert result["payload"]["decision"] == "pass"
    assert record is not None and len(record.tool_calls) == 2
    request = runtime.requests[0]
    assert request.editable_paths == ()
    assert request.tool_policies["Read"].max_calls == 2
    assert "source_reconstruction" in request.prompt
    assert "不读取图片、视频、帧或联系图" in request.prompt


def test_reviewer_retries_when_one_source_was_not_read(tmp_path) -> None:
    candidate, figure = _sources(tmp_path)
    runtime = Runtime(miss_figure_once=True)

    run_figure_fidelity_reviewer(
        runtime, candidate_path=candidate, figure_path=figure,
        problem_text="如图。", model="test-model",
    )

    assert len(runtime.requests) == 2
    assert runtime.requests[-1].run_id.endswith("-native-read-retry")


def test_missing_figure_is_not_applicable(tmp_path, monkeypatch) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n    pass\n", encoding="utf-8")
    monkeypatch.delenv("MATHPI_RENDER_ASSETS_DIR", raising=False)

    assert locate_confirmed_figure(candidate) is None
    assert run_figure_fidelity_reviewer(
        Runtime(), candidate_path=candidate, problem_text="计算。",
        model="test-model",
    ) == (None, None)


def test_auto_repair_requires_high_confidence_and_normalizes_decision() -> None:
    issue = {"repair_action": "auto_repair", "confidence": 0.9}
    _validate_output({"decision": "needs_repair", "issues": [issue]})
    _validate_output({"decision": "pass", "issues": [issue]})
    assert _decision([issue]) == "needs_repair"
    assert _decision([{"repair_action": "evidence_only"}]) == "pass"
    issue["confidence"] = 0.7
    with pytest.raises(ValueError, match="confidence"):
        _validate_output({"decision": "needs_repair", "issues": [issue]})
