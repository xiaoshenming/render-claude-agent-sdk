
import json

from dataclasses import replace

from pathlib import Path

import anyio

import pytest

from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock

from mcp.types import CallToolRequest

from manim_quality.agents._runtime_models import CorrectableOutputError

from manim_quality.agents.budget import BudgetLimits

from manim_quality.agents.claude_sdk import ClaudeSdkBackend

from manim_quality.agents.profile import reviewer_profile

from manim_quality.agents.read_tools import ReadonlyToolGrant

from manim_quality.agents.runtime import AgentRunFailed, AgentRunRequest, AgentRuntime

from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink

class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)

def limits(*, max_turns: int = 2, max_tool_calls: int = 2) -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=100_000,
        max_turns=max_turns,
        max_tool_calls=max_tool_calls,
        max_elapsed_ms=10_000,
        max_input_tokens=1_000,
        max_output_tokens=500,
        max_cache_read_tokens=500,
        max_cache_write_tokens=500,
        max_total_tokens=2_000,
    )

def request(workspace: Path, candidate: Path) -> AgentRunRequest:
    return AgentRunRequest(
        run_id="sdk-1",
        profile=reviewer_profile(model="fake-model", prompt_version="logic-v1"),
        prompt="Review candidate.py and return structured output.",
        output_schema={"type": "object", "required": ["decision"]},
        workspace=workspace,
        readable_paths=(candidate,),
        editable_paths=(),
        context_bytes=1_000,
        estimated_input_tokens=200,
        reserved_output_tokens=100,
        reserved_cache_read_tokens=50,
        reserved_cache_write_tokens=50,
    )

def inspect_relation(arguments):
    return f"relation={arguments['relation']}"

def geometry_tool() -> ReadonlyToolGrant:
    return ReadonlyToolGrant(
        server_name="geometry",
        name="inspect_relation",
        description="Inspect one geometry relation.",
        input_schema={
            "type": "object",
            "properties": {"relation": {"type": "string"}},
            "required": ["relation"],
            "additionalProperties": False,
        },
        handler=inspect_relation,
        max_calls=2,
        timeout_ms=100,
        max_result_chars=200,
    )

def result_message(*, turns: int = 2, usage: dict | None = None) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=turns,
        session_id="session-1",
        usage=usage,
        structured_output={"decision": "pass"},
    )

@pytest.mark.parametrize(
    "sdk_path",
    ["\\workspace\\candidate.py", "\\candidate.py"],
)
def test_sdk_backend_binds_options_hooks_rounds_and_usage(
    tmp_path: Path, sdk_path: str
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    captured = {}

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["options"] = options
        pre = options.hooks["PreToolUse"][0].hooks[0]
        post = options.hooks["PostToolUse"][0].hooks[0]
        hook_input = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "transcript_path": "ignored",
            "cwd": str(tmp_path),
            "tool_name": "Read",
            "tool_input": {"file_path": sdk_path},
            "tool_use_id": "tool-1",
        }
        permission = await pre(hook_input, "tool-1", {"signal": None})
        captured["permission"] = permission
        yield AssistantMessage(
            content=[ToolUseBlock(id="tool-1", name="Read", input={})],
            model="fake-model",
            message_id="message-1",
            usage={
                "input_tokens": 50,
                "output_tokens": 10,
                "cache_read_input_tokens": 5,
                "cache_creation_input_tokens": 2,
            },
        )
        await post(
            hook_input | {"hook_event_name": "PostToolUse", "tool_response": {}},
            "tool-1",
            {"signal": None},
        )
        final_message = AssistantMessage(
            content=[],
            model="fake-model",
            message_id="message-2",
            usage={"input_tokens": 70, "output_tokens": 20},
        )
        yield final_message
        yield final_message
        yield result_message(
            turns=2,
            usage={
                "input_tokens": 120,
                "output_tokens": 30,
                "cache_read_input_tokens": 5,
                "cache_creation_input_tokens": 2,
            },
        )

    sink = MemorySink()
    runtime = AgentRuntime(ClaudeSdkBackend(query_func=fake_query), sink, limits())

    outcome = runtime.run(request(tmp_path, candidate))

    assert outcome.structured_output == {"decision": "pass"}
    assert outcome.record.turns == 2
    assert outcome.record.observed_model_rounds == 2
    assert outcome.record.usage == TokenUsage(
        input_tokens=120,
        output_tokens=30,
        cache_read_tokens=5,
        cache_write_tokens=2,
    )
    options = captured["options"]
    assert options.tools == ["Read"]
    assert options.allowed_tools == ["Read"]
    assert options.permission_mode == "dontAsk"
    assert options.setting_sources == []
    assert options.skills == []
    assert options.strict_mcp_config is True
    assert options.max_turns == 2
    assert options.output_format["schema"] == {
        "type": "object",
        "required": ["decision"],
    }
    assert captured["permission"]["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert captured["permission"]["hookSpecificOutput"]["updatedInput"][
        "file_path"
    ] == str(candidate.resolve())

def test_sdk_backend_mounts_only_explicit_in_process_read_tools(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = geometry_tool()
    captured = {}

    async def fake_query(*, prompt, options):
        captured["options"] = options
        yield AssistantMessage(
            content=[],
            model="fake-model",
            message_id="message-1",
            usage={"input_tokens": 1, "output_tokens": 1},
        )
        yield result_message(
            turns=1,
            usage={"input_tokens": 1, "output_tokens": 1},
        )

    runtime = AgentRuntime(
        ClaudeSdkBackend(query_func=fake_query), MemorySink(), limits()
    )

    runtime.run(replace(request(tmp_path, candidate), read_tools=(tool,)))

    options = captured["options"]
    assert options.tools == ["Read"]
    assert options.allowed_tools == ["Read", tool.sdk_name]
    assert tuple(options.mcp_servers) == ("geometry",)
    assert options.mcp_servers["geometry"]["type"] == "sdk"

def test_sdk_read_tool_traverses_hooks_provider_and_hashed_audit(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = geometry_tool()

    async def fake_query(*, prompt, options):
        pre = options.hooks["PreToolUse"][0].hooks[0]
        post = options.hooks["PostToolUse"][0].hooks[0]
        arguments = {"relation": "perpendicular"}
        hook_input = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "transcript_path": "ignored",
            "cwd": str(tmp_path),
            "tool_name": tool.sdk_name,
            "tool_input": arguments,
            "tool_use_id": "geometry-1",
        }
        permission = await pre(hook_input, "geometry-1", {"signal": None})
        assert permission["hookSpecificOutput"]["permissionDecision"] == "allow"
        server = options.mcp_servers["geometry"]["instance"]
        handler = server.request_handlers[CallToolRequest]
        response = await handler(
            CallToolRequest(
                params={"name": tool.name, "arguments": arguments}
            )
        )
        assert response.root.content[0].text == "relation=perpendicular"
        yield AssistantMessage(
            content=[
                ToolUseBlock(
                    id="geometry-1", name=tool.sdk_name, input=arguments
                )
            ],
            model="fake-model",
            message_id="message-1",
            usage={"input_tokens": 1, "output_tokens": 1},
        )
        await post(
            hook_input | {"hook_event_name": "PostToolUse", "tool_response": {}},
            "geometry-1",
            {"signal": None},
        )
        yield AssistantMessage(
            content=[],
            model="fake-model",
            message_id="message-2",
            usage={"input_tokens": 1, "output_tokens": 1},
        )
        yield result_message(
            turns=2,
            usage={"input_tokens": 2, "output_tokens": 2},
        )

    outcome = AgentRuntime(
        ClaudeSdkBackend(query_func=fake_query), MemorySink(), limits()
    ).run(replace(request(tmp_path, candidate), read_tools=(tool,)))

    call = outcome.record.tool_calls[0]
    assert call.name == tool.sdk_name
    assert call.result_status == "ok"
    assert call.result_hash is not None and call.result_hash.startswith("sha256:")
