from __future__ import annotations

from pathlib import Path

import pytest

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.profile import coder_profile, reviewer_profile
from manim_quality.agents.runtime import AgentRuntime, BackendRequest, RuntimeControls
from manim_quality.agents.usage import AgentCallRecord, TokenUsage
from manim_quality.modification.coder import ModificationCoder
from manim_quality.modification.planner import plan_modification

SOURCE = """\
class Intro(Scene):
    def construct(self):
        self.add(Text("old"))
"""


class EditBackend:
    def __init__(self) -> None:
        self.allowed_tools: tuple[str, ...] = ()

    def run(self, request: BackendRequest, controls: RuntimeControls):
        self.allowed_tools = request.allowed_tools
        path = Path(request.editable_paths[0])
        controls.authorize_tool(
            "Edit",
            {
                "file_path": str(path),
                "old_string": 'Text("old")',
                "new_string": 'Text("fixed")',
            },
        )
        path.write_text(
            path.read_text(encoding="utf-8").replace('Text("old")', 'Text("fixed")'),
            encoding="utf-8",
        )
        controls.record_round_usage(TokenUsage(input_tokens=20, output_tokens=5))
        return controls.complete({"status": "edited", "summary": "updated Intro"})


class Sink:
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


def test_modification_coder_uses_read_edit_runtime_and_scope_guard() -> None:
    backend = EditBackend()
    coder = ModificationCoder(
        AgentRuntime(backend, Sink(), _limits()),
        coder_profile(model="model-v1", prompt_version="user-mod-v1"),
    )

    result = coder.patch_source(
        run_id="modify-1",
        instruction="Correct the label.",
        source_code=SOURCE,
        plan=plan_modification(SOURCE, ("Intro",)),
    )

    assert 'Text("fixed")' in result.source_code
    assert result.changed_scene_ids == ("Intro",)
    assert backend.allowed_tools == ("Edit", "Read")


def test_modification_coder_rejects_read_only_profile() -> None:
    with pytest.raises(ValueError, match=r"Read\+Edit"):
        ModificationCoder(
            AgentRuntime(EditBackend(), Sink(), _limits()),
            reviewer_profile(model="model-v1", prompt_version="review-v1"),
        )


def _limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=100_000,
        max_turns=3,
        max_tool_calls=3,
        max_elapsed_ms=10_000,
        max_input_tokens=10_000,
        max_output_tokens=3_000,
        max_cache_read_tokens=1_000,
        max_cache_write_tokens=1_000,
        max_total_tokens=15_000,
    )
