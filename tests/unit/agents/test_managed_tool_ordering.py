import anyio

from manim_quality.agents._claude_hook_accessors import ClaudeHookAccessors
from manim_quality.agents._guard_primitives import ToolDenied


class Controls:
    def __init__(self) -> None:
        self.authorized = False
        self.authorize_calls = 0

    async def execute_managed_tool_content(self, name, input_data):
        if not self.authorized:
            raise ToolDenied(
                f"managed tool has no pending authorization: {name}")
        return ({"type": "text", "text": input_data["case_key"]},)

    def authorize_tool(self, name, input_data, *, call_id=None):
        del name, call_id
        self.authorized = True
        self.authorize_calls += 1
        return input_data


def test_mcp_handler_can_arrive_before_pretooluse_hook() -> None:
    accessor = ClaudeHookAccessors()
    accessor._controls = Controls()

    result = anyio.run(
        accessor.execute_managed_tool_content,
        "mcp__assurance__inspect_artifact",
        {"case_key": "case"},
    )

    assert result[0]["text"] == "case"
    assert accessor._controls.authorize_calls == 1
