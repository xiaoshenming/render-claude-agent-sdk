
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

def test_sdk_backend_distinguishes_reserved_from_observed_rounds(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    async def fake_query(*, prompt, options):
        pre = options.hooks["PreToolUse"][0].hooks[0]
        item = {
            "hook_event_name": "PreToolUse",
            "session_id": "session-1",
            "transcript_path": "ignored",
            "cwd": str(tmp_path),
            "tool_name": "StructuredOutput",
            "tool_input": {"wrong": True},
            "tool_use_id": "rejected",
        }
        await pre(item, "rejected", {"signal": None})
        yield AssistantMessage(
            content=[ToolUseBlock(id="rejected", name="StructuredOutput", input={})],
            model="fake-model",
            message_id="message-1",
            usage={"input_tokens": 40, "output_tokens": 10},
        )
        raise RuntimeError("transport failed before correction response")

    def reject_output(_value) -> None:
        raise CorrectableOutputError("model output is invalid")

    sink = MemorySink()
    runtime = AgentRuntime(ClaudeSdkBackend(query_func=fake_query), sink, limits())

    with pytest.raises(AgentRunFailed, match="transport failed"):
        runtime.run(
            replace(request(tmp_path, candidate), output_validator=reject_output)
        )

    assert sink.records[0].turns == 1
    assert sink.records[0].observed_model_rounds == 1
