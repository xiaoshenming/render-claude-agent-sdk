"""Reviewer group orchestration stays parallel and provider-neutral."""

from types import SimpleNamespace

from manim_quality.agents.profile import AgentRole
from manim_quality.agents.usage import ToolCallRecord
from manim_quality.operator.parallel_reviewer_sessions import REVIEWER_SCHEMA
from manim_quality.operator.reviewers import run_reviewers


def _payload() -> dict[str, object]:
    return {
        "decision": "pass",
        "diagnosis": "ok",
        "issues": [],
        "coverage": {},
        "confidence": 1.0,
    }


class Runtime:
    def __init__(self, *, metadata=True, invalid_figure=False) -> None:
        self.requests = []
        self.metadata = metadata
        self.invalid_figure = invalid_figure

    def run(self, request):
        self.requests.append(request)
        payload = _payload()
        if self.invalid_figure and "figure_fidelity_reviewer" in request.run_id:
            payload["issues"] = [{"repair_action": "provider_specific"}]
        record = SimpleNamespace(
            usage=SimpleNamespace(total_tokens=40),
            tool_calls=tuple(
                ToolCallRecord(name=tool.sdk_name, input={}, allowed=True)
                for tool in request.managed_tools
            ) if self.metadata else (),
            usage_complete=True,
            model="test-model",
            elapsed_ms=10,
            turns=1,
        )
        return SimpleNamespace(structured_output=payload, record=record)


def test_reviewers_use_one_parent_with_four_native_subagents(tmp_path) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n    def construct(self):\n        pass\n",
        encoding="utf-8",
    )
    figure = tmp_path / "assets/visual/figure.py"
    figure.parent.mkdir(parents=True)
    figure.write_text("class Figure: pass\n", encoding="utf-8")
    runtime = Runtime()

    reviewers, records = run_reviewers(
        runtime,
        candidate_path=candidate,
        problem_text="求解。",
        parsed_standard_answer="标准推导，所以选择B。",
        teaching_script="五段式讲解。",
        reviewer_supplemental_notes={
            "review1_math_logic": "核对选择题结论",
            "review2_animation_lifecycle": "关注结论停留",
            "review3_visual_layout": "关注右侧安全区",
            "review4_figure_fidelity": "保持原图方向",
        },
        model="test-model",
    )

    assert len(runtime.requests) == 4
    assert all(r.profile.role is AgentRole.REVIEWER for r in runtime.requests)
    assert all(not r.subagents for r in runtime.requests)
    assert {r.run_id.split("-")[1] for r in runtime.requests} == {
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
        "visual_layout_reviewer",
        "figure_fidelity_reviewer",
    }
    assert [item["agent_type"] for item in reviewers] == [
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
        "visual_layout_reviewer",
        "figure_fidelity_reviewer",
    ]
    assert len(records) == 4
    prompts = {r.run_id.split("-")[1]: r.prompt for r in runtime.requests}
    assert "标准推导，所以选择B。" in prompts["math_geometry_reviewer"]
    assert "五段式讲解。" in prompts["math_geometry_reviewer"]
    assert "核对选择题结论" in prompts["math_geometry_reviewer"]
    assert "五段式讲解。" in prompts["animation_lifecycle_reviewer"]
    assert "求解。" not in prompts["animation_lifecycle_reviewer"]
    assert "标准推导" not in prompts["animation_lifecycle_reviewer"]
    assert "关注右侧安全区" in prompts["visual_layout_reviewer"]
    assert "五段式讲解。" not in prompts["visual_layout_reviewer"]
    assert "保持原图方向" in prompts["figure_fidelity_reviewer"]
    assert "求解。" not in prompts["figure_fidelity_reviewer"]
    assert "五段式讲解。" not in prompts["figure_fidelity_reviewer"]


def test_reviewer_schema_is_openai_strict_compatible() -> None:
    def check(node) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            properties = node.get("properties", {})
            assert node.get("additionalProperties") is False
            assert set(node.get("required", ())) == set(properties)
        for value in node.values():
            if isinstance(value, dict):
                check(value)
            elif isinstance(value, list):
                for item in value:
                    check(item)

    check(REVIEWER_SCHEMA)


def test_missing_sdk_tool_count_is_evidence_not_a_blocker(tmp_path) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n    def construct(self):\n        pass\n",
        encoding="utf-8",
    )
    runtime = Runtime(metadata=False)

    reviewers, _ = run_reviewers(
        runtime,
        candidate_path=candidate,
        problem_text="求解。",
        solution_steps="完成证明。",
        model="test-model",
    )

    assert len(reviewers) == 3
    assert reviewers[0]["protocol_warnings"] == ["native_tool_count:None/1"]


def test_nonstandard_figure_action_is_evidence_not_a_blocker(tmp_path) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n    def construct(self):\n        pass\n",
        encoding="utf-8",
    )
    figure = tmp_path / "assets/visual/figure.py"
    figure.parent.mkdir(parents=True)
    figure.write_text("class Figure: pass\n", encoding="utf-8")

    reviewers, _ = run_reviewers(
        Runtime(invalid_figure=True),
        candidate_path=candidate,
        problem_text="求解。",
        solution_steps="完成证明。",
        model="test-model",
    )

    figure_review = reviewers[-1]
    assert figure_review["payload"]["decision"] == "needs_repair"
    assert "figure_payload_nonstandard" in figure_review["protocol_warnings"][0]
