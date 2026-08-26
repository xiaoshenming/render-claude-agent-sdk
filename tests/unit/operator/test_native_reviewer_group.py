"""One parent session must own all foreground reviewer subagents."""

from types import SimpleNamespace

from manim_quality.agents.profile import AgentRole
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
    def __init__(self, *, metadata=True) -> None:
        self.requests = []
        self.metadata = metadata

    def run(self, request):
        self.requests.append(request)
        rows = []
        for index, spec in enumerate(request.subagents):
            payload = _payload()
            rows.append(
                {
                    "agent_type": spec.name,
                    "agent_id": f"agent-{index}",
                    "is_error": False,
                    "payload": payload,
                    "raw_payload": payload,
                    "sdk_metadata": {
                        "subagent_tokens": 10,
                        "tool_uses": len(spec.allowed_tools),
                        "duration_ms": 5,
                    } if self.metadata else None,
                }
            )
        record = SimpleNamespace(
            usage=SimpleNamespace(total_tokens=40),
            tool_calls=(),
            usage_complete=True,
            model="test-model",
            elapsed_ms=10,
            turns=1,
        )
        return SimpleNamespace(subagent_results=tuple(rows), record=record)


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
        solution_steps="完成证明。",
        model="test-model",
    )

    assert len(runtime.requests) == 1
    request = runtime.requests[0]
    assert request.profile.role is AgentRole.ASSURANCE
    assert [item.name for item in request.subagents] == [
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
        "visual_layout_reviewer",
        "figure_fidelity_reviewer",
    ]
    assert [item["agent_type"] for item in reviewers] == [
        item.name for item in request.subagents
    ]
    assert len(records) == 1


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
