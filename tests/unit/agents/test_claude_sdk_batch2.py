
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

def test_sdk_backend_denies_unmanaged_tool_and_fails_run(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    async def fake_query(*, prompt, options):
        pre = options.hooks["PreToolUse"][0].hooks[0]
        permission = await pre(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "session-1",
                "transcript_path": "ignored",
                "cwd": str(tmp_path),
                "tool_name": "Bash",
                "tool_input": {"command": "echo no"},
                "tool_use_id": "tool-denied",
            },
            "tool-denied",
            {"signal": None},
        )
        assert permission["hookSpecificOutput"]["permissionDecision"] == "deny"
        yield result_message(turns=1, usage={"input_tokens": 1, "output_tokens": 1})

    sink = MemorySink()
    runtime = AgentRuntime(ClaudeSdkBackend(query_func=fake_query), sink, limits())

    with pytest.raises(AgentRunFailed, match="not allowed"):
        runtime.run(request(tmp_path, candidate))

    assert sink.records[0].tool_calls[0].name == "Bash"
    assert sink.records[0].tool_calls[0].allowed is False

def test_sdk_backend_allows_only_schema_bound_structured_output(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    async def fake_query(*, prompt, options):
        pre = options.hooks["PreToolUse"][0].hooks[0]
        post = options.hooks["PostToolUse"][0].hooks[0]
        hook_input = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "transcript_path": "ignored",
            "cwd": str(tmp_path),
            "tool_name": "StructuredOutput",
            "tool_input": {
                "decision": "pass",
                "details": {"items": [{"line": 1}]},
            },
            "tool_use_id": "structured-1",
        }
        permission = await pre(hook_input, "structured-1", {"signal": None})
        assert permission["hookSpecificOutput"]["permissionDecision"] == "allow"
        json.dumps(permission)
        read_input = {
            **hook_input,
            "tool_name": "Read",
            "tool_input": {"file_path": "\\workspace\\candidate.py"},
            "tool_use_id": "read-1",
        }
        await pre(read_input, "read-1", {"signal": None})
        yield AssistantMessage(
            content=[],
            model="fake-model",
            message_id="message-1",
            usage={"input_tokens": 40, "output_tokens": 10},
        )
        tool_message = AssistantMessage(
            content=[
                ToolUseBlock(
                    id="structured-1",
                    name="StructuredOutput",
                    input={"decision": "pass"},
                ),
                ToolUseBlock(id="read-1", name="Read", input={}),
            ],
            model="fake-model",
            message_id="message-1",
            usage={"input_tokens": 40, "output_tokens": 10},
        )
        yield tool_message
        yield tool_message
        await post(
            hook_input | {"hook_event_name": "PostToolUse", "tool_response": {}},
            "structured-1",
            {"signal": None},
        )
        await post(
            read_input | {"hook_event_name": "PostToolUse", "tool_response": {}},
            "read-1",
            {"signal": None},
        )
        yield result_message(
            turns=2,
            usage={"input_tokens": 40, "output_tokens": 10},
        )

    sink = MemorySink()
    runtime = AgentRuntime(ClaudeSdkBackend(query_func=fake_query), sink, limits())

    outcome = runtime.run(request(tmp_path, candidate))

    assert outcome.structured_output == {"decision": "pass"}
    assert outcome.record.turns == 2
    assert outcome.record.observed_model_rounds == 1
    structured = next(
        call for call in sink.records[0].tool_calls if call.name == "StructuredOutput"
    )
    assert structured.allowed is True

def test_sdk_backend_grants_only_one_concurrent_output_correction(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    async def fake_query(*, prompt, options):
        failed = options.hooks["PostToolUseFailure"][0].hooks[0]
        attempts = []
        for tool_id in ("structured-1", "structured-2"):
            item = {
                "hook_event_name": "PreToolUse",
                "session_id": "session-1",
                "transcript_path": "ignored",
                "cwd": str(tmp_path),
                "tool_name": "StructuredOutput",
                "tool_input": {"wrong": True},
                "tool_use_id": tool_id,
            }
            attempts.append(item)
        yield AssistantMessage(
            content=[
                ToolUseBlock(id=item["tool_use_id"], name="StructuredOutput", input={})
                for item in attempts
            ],
            model="fake-model",
            message_id="message-1",
            usage={"input_tokens": 40, "output_tokens": 10},
        )

        async def reject(item):
            await failed(
                item
                | {
                    "hook_event_name": "PostToolUseFailure",
                    "error": "schema mismatch",
                },
                item["tool_use_id"],
                {"signal": None},
            )

        async with anyio.create_task_group() as group:
            for item in attempts:
                group.start_soon(reject, item)
        yield result_message(turns=3, usage={"input_tokens": 40, "output_tokens": 10})

    sink = MemorySink()
    runtime = AgentRuntime(
        ClaudeSdkBackend(query_func=fake_query),
        sink,
        limits(max_turns=2, max_tool_calls=3),
    )

    with pytest.raises(AgentRunFailed):
        runtime.run(request(tmp_path, candidate))

    assert [call.name for call in sink.records[0].tool_calls].count(
        "StructuredOutputCorrection"
    ) == 1

def test_sdk_backend_requires_per_turn_usage(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    async def fake_query(*, prompt, options):
        yield AssistantMessage(content=[], model="fake-model", usage=None)
        yield result_message(turns=1, usage=None)

    runtime = AgentRuntime(
        ClaudeSdkBackend(query_func=fake_query), MemorySink(), limits()
    )

    with pytest.raises(AgentRunFailed, match="usage"):
        runtime.run(request(tmp_path, candidate))
