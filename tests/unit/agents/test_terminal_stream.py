"""A terminal result ends a response even when the upstream stream stays open."""

from dataclasses import replace

import anyio
import pytest
from claude_agent_sdk import AssistantMessage, ClaudeSDKClient

from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.runtime import AgentRunFailed, AgentRuntime
from tests.unit.agents.test_claude_sdk import (
    MemorySink,
    limits,
    request,
    result_message,
)


@pytest.mark.parametrize("mode", ["success", "error", "invalid-message", "timeout"])
def test_terminal_result_closes_stream_in_same_task(tmp_path, monkeypatch, mode):
    events = []

    class FakeClient:
        receive_response = ClaudeSDKClient.receive_response

        def __init__(self, *, options):
            self.options = options

        async def __aenter__(self):
            self.owner = anyio.get_current_task().id
            self.group = anyio.create_task_group()
            await self.group.__aenter__()
            return self

        async def __aexit__(self, *args):
            assert anyio.get_current_task().id == self.owner
            self.group.cancel_scope.cancel()
            await self.group.__aexit__(None, None, None)
            events.append("closed")

        async def query(self, prompt):
            assert prompt

        async def receive_messages(self):
            if mode == "timeout":
                await anyio.sleep_forever()
            yield AssistantMessage(
                content=[],
                model="fake-model",
                message_id="a",
                usage=None
                if mode == "invalid-message"
                else {"input_tokens": 1, "output_tokens": 1},
            )
            yield replace(
                result_message(turns=1, usage={"input_tokens": 1, "output_tokens": 1}),
                is_error=mode == "error",
                errors=["provider failed"] if mode == "error" else None,
            )
            events.append("continued-after-terminal")
            await anyio.sleep_forever()

    monkeypatch.setattr(
        "manim_quality.agents._query_lifecycle.ClaudeSDKClient", FakeClient
    )

    req = replace(request(tmp_path, tmp_path / "unused"), readable_paths=())
    runtime = AgentRuntime(
        ClaudeSdkBackend(),
        MemorySink(),
        replace(limits(), max_elapsed_ms=100),
    )
    if mode != "success":
        error = {
            "error": "provider failed",
            "invalid-message": "usage is required",
            "timeout": "reasoning budget",
        }[mode]
        with pytest.raises(AgentRunFailed, match=error):
            runtime.run(req)
    else:
        assert runtime.run(req).structured_output == {"decision": "pass"}
    assert events == ["closed"]
