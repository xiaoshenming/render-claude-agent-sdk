"""Evidence projection is identical for tool, result and text-only responses."""

import json
from dataclasses import replace

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

from manim_quality.agents._runtime_models import CorrectableOutputError
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.runtime import AgentRunFailed, AgentRuntime
from tests.unit.agents.test_claude_sdk import MemorySink, limits, request

SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["review"]},
        "summary": {"type": "string"},
        "receipt": {"type": "string", "enum": ["observed-id"]},
    },
    "required": ["decision", "summary", "receipt"],
    "additionalProperties": False,
}


@pytest.mark.parametrize("transport", ["tool", "result", "text"])
def test_projection_precedes_submission_and_recovery_validation(tmp_path, transport):
    emitted = {"decision": "review", "summary": "模型的原始判断"}
    expected = emitted | {"receipt": "observed-id"}
    seen = []

    def project(value):
        return dict(value) | {"receipt": "observed-id"}

    def validate(value):
        seen.append(dict(value))
        if value != expected:
            raise CorrectableOutputError("receipt or model assessment changed")

    async def query(*, prompt, options):
        content = [TextBlock(text=json.dumps(emitted))]
        if transport == "tool":
            data = {
                "tool_name": "StructuredOutput",
                "tool_input": emitted,
                "tool_use_id": "output-1",
            }
            permission = await options.hooks["PreToolUse"][0].hooks[0](
                data, "output-1", {}
            )
            assert permission["hookSpecificOutput"]["updatedInput"] == expected
            content = [
                ToolUseBlock(id="output-1", name="StructuredOutput", input=emitted)
            ]
        yield AssistantMessage(
            content=content,
            model="fake-model",
            message_id="a",
            usage={"input_tokens": 1, "output_tokens": 1},
        )
        if transport == "tool":
            await options.hooks["PostToolUse"][0].hooks[0](
                data | {"tool_response": {}}, "output-1", {}
            )
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s",
            usage={"input_tokens": 1, "output_tokens": 1},
            structured_output=emitted if transport == "result" else None,
        )

    req = replace(
        request(tmp_path, tmp_path / "candidate.py"),
        output_schema=SCHEMA,
        output_validator=validate,
        output_normalizer=project,
        readable_paths=(),
    )
    outcome = AgentRuntime(
        ClaudeSdkBackend(query_func=query), MemorySink(), limits()
    ).run(req)
    assert outcome.structured_output == expected
    assert seen and all(value == expected for value in seen)


def test_projection_does_not_make_invalid_model_decision_schema_valid(tmp_path):
    async def query(*, prompt, options):
        yield AssistantMessage(
            content=[TextBlock(text='{"decision":"invented","summary":"unchanged"}')],
            model="fake-model",
            message_id="a",
            usage={"input_tokens": 1, "output_tokens": 1},
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s",
            usage={"input_tokens": 1, "output_tokens": 1},
        )

    req = replace(
        request(tmp_path, tmp_path / "candidate.py"),
        output_schema=SCHEMA,
        output_normalizer=lambda value: dict(value) | {"receipt": "observed-id"},
        readable_paths=(),
    )
    with pytest.raises(AgentRunFailed, match="no structured output"):
        AgentRuntime(ClaudeSdkBackend(query_func=query), MemorySink(), limits()).run(
            req
        )
