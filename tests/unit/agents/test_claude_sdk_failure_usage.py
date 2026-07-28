"""Regression coverage for terminal usage on failed Agent sessions."""

from pathlib import Path

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage

from manim_quality.agents._runtime_models import AgentRunFailed
from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import AgentRunRequest, AgentRuntime
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


def _limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=100_000,
        max_turns=3,
        max_tool_calls=3,
        max_elapsed_ms=10_000,
        max_input_tokens=2_000,
        max_output_tokens=1_000,
        max_cache_read_tokens=2_000,
        max_cache_write_tokens=1_000,
        max_total_tokens=6_000,
    )


def _request(workspace: Path) -> AgentRunRequest:
    candidate = workspace / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    return AgentRunRequest(
        run_id="failed-usage",
        profile=reviewer_profile(model="test-model", prompt_version="v1"),
        prompt="Review the candidate.",
        output_schema={"type": "object"},
        workspace=workspace,
        readable_paths=(candidate,),
        editable_paths=(),
        context_bytes=100,
        estimated_input_tokens=10,
        reserved_output_tokens=10,
        reserved_cache_read_tokens=10,
        reserved_cache_write_tokens=10,
    )


def _terminal_error() -> ResultMessage:
    return ResultMessage(
        subtype="error_max_turns",
        duration_ms=500,
        duration_api_ms=400,
        is_error=True,
        num_turns=1,
        session_id="session-failed",
        usage={"input_tokens": 80, "output_tokens": 20},
        model_usage={
            "test-model": {
                "inputTokens": 80,
                "outputTokens": 20,
                "cacheReadInputTokens": 120,
                "cacheCreationInputTokens": 5,
            },
        },
        errors=["maximum turns reached"],
    )


def test_failed_result_reconciles_and_retains_terminal_usage(tmp_path: Path) -> None:
    async def fake_query(*, prompt, options):
        del prompt, options
        yield AssistantMessage(
            content=[],
            model="test-model",
            message_id="round-1",
            usage={"input_tokens": 30, "output_tokens": 5},
        )
        yield _terminal_error()

    sink = MemorySink()
    runtime = AgentRuntime(
        ClaudeSdkBackend(query_func=fake_query),
        sink,
        _limits(),
    )

    with pytest.raises(AgentRunFailed) as caught:
        runtime.run(_request(tmp_path))

    record = caught.value.record
    assert record.usage_complete is True
    assert record.usage == TokenUsage(
        input_tokens=80,
        output_tokens=20,
        cache_read_tokens=120,
        cache_write_tokens=5,
    )
    terminal = caught.value.sdk_messages[-1]
    assert terminal["kind"] == "result"
    assert terminal["is_error"] is True
    assert terminal["model_usage"]["test-model"]["inputTokens"] == 80
    assert sink.records == [record]
