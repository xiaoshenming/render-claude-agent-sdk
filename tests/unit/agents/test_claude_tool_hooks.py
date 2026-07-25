import anyio

from manim_quality.agents._claude_tool_hooks import recover_managed_failure


class RecoverableState:
    def __init__(self) -> None:
        self.finished = []

    async def _finish_tool(self, tool_id: str) -> dict[str, object]:
        self.finished.append(tool_id)
        return {}


def test_managed_tool_failure_returns_correction_to_agent() -> None:
    state = RecoverableState()
    result = anyio.run(
        recover_managed_failure,
        state,
        {
            "tool_use_id": "validate-1",
            "error": "only the current candidate can be validated",
        },
    )

    assert state.finished == ["validate-1"]
    assert result["continue_"] is True
    assert "current candidate" in result["hookSpecificOutput"]["additionalContext"]
