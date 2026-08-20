from pathlib import Path
from types import SimpleNamespace

import pytest

from manim_quality.operator.figure_fidelity import (
    _decision,
    _normalize_actions,
    _validate_output,
    locate_confirmed_figure,
    run_figure_fidelity_reviewer,
)
from manim_quality.operator.reviewers import run_reviewers


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


def test_unified_reviewers_append_figure_reviewer_when_asset_exists(tmp_path) -> None:
    candidate, _figure = _sources(tmp_path)
    runtime = Runtime()

    reviewers, records = run_reviewers(
        runtime, candidate_path=candidate, problem_text="如图。",
        model="test-model",
    )

    assert [item["agent_type"] for item in reviewers] == [
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
        "visual_layout_reviewer",
        "figure_fidelity_reviewer",
    ]
    assert len(records) == 4


def test_action_normalization_prevents_unsafe_auto_repair() -> None:
    conflict = {
        "repair_action": "auto_repair", "authority_status": "contradicted",
        "source_role": "required_input",
        "source_presence": "present",
        "temporal_status": "corresponding_stage_mismatch",
        "semantic_equivalence": False,
        "difference_scope": "base_figure",
    }
    equivalent = {
        "repair_action": "auto_repair", "authority_status": "supported",
        "source_role": "required_input", "temporal_status": "not_applicable",
        "source_presence": "present",
        "semantic_equivalence": True,
        "difference_scope": "decorative",
    }
    supported = {
        "repair_action": "auto_repair", "authority_status": "supported",
        "source_role": "required_input",
        "source_presence": "present",
        "temporal_status": "corresponding_stage_mismatch",
        "semantic_equivalence": False,
        "difference_scope": "base_figure",
    }
    runtime_panel = {
        "repair_action": "auto_repair", "authority_status": "supported",
        "source_role": "required_input",
        "source_presence": "present",
        "temporal_status": "corresponding_stage_mismatch",
        "semantic_equivalence": False,
        "difference_scope": "runtime_problem_panel",
    }
    later_solution = {
        "repair_action": "auto_repair", "authority_status": "supported",
        "source_role": "required_input",
        "source_presence": "present",
        "temporal_status": "corresponding_stage_mismatch",
        "semantic_equivalence": False,
        "difference_scope": "later_solution_content",
    }
    absent_source = {
        "repair_action": "auto_repair", "authority_status": "supported",
        "source_role": "required_input", "source_presence": "absent",
        "temporal_status": "corresponding_stage_mismatch",
        "semantic_equivalence": False, "difference_scope": "base_figure",
    }

    assert _normalize_actions([
        conflict, equivalent, supported, runtime_panel, later_solution,
        absent_source,
    ]) == 5
    assert conflict["repair_action"] == "human_review"
    assert equivalent["repair_action"] == "evidence_only"
    assert supported["repair_action"] == "auto_repair"
    assert runtime_panel["repair_action"] == "evidence_only"
    assert later_solution["repair_action"] == "human_review"
    assert absent_source["repair_action"] == "human_review"
