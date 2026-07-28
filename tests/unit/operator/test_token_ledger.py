import json
from types import MappingProxyType

from manim_quality.agents.usage import AgentCallRecord, TokenUsage
from manim_quality.operator.artifact_usage import token_ledger


def test_token_ledger_retains_round_terminal_and_reviewer_attribution() -> None:
    record = AgentCallRecord(
        run_id="run-1",
        role="quality_operator",
        model="test-model",
        prompt="prompt",
        prompt_version="v1",
        schema_version="v1",
        tool_version="v1",
        structured_output=None,
        tool_calls=(),
        usage=TokenUsage(
            input_tokens=100,
            output_tokens=20,
            cache_read_tokens=30,
            cache_write_tokens=4,
        ),
        turns=2,
        observed_model_rounds=2,
        elapsed_ms=100,
        error="maximum turns reached",
        usage_complete=True,
    )
    messages = ({
        "kind": "assistant",
        "message_id": "parent-1",
        "parent_tool_use_id": None,
        "model": "test-model",
        "usage": {"input_tokens": 40, "output_tokens": 5},
    }, {
        "kind": "assistant",
        "message_id": "reviewer-1",
        "parent_tool_use_id": "agent-1",
        "model": "test-model",
        "usage": {"input_tokens": 20, "output_tokens": 3},
    }, {
        "kind": "result",
        "subtype": "error_max_turns",
        "is_error": True,
        "num_turns": 2,
        "session_id": "session-1",
        "usage": {"input_tokens": 100, "output_tokens": 20},
        "model_usage": {"test-model": {"inputTokens": 100}},
    })
    reviewers = ({
        "agent_id": "reviewer-id",
        "agent_type": "math_geometry_reviewer",
        "sdk_metadata": {
            "subagent_tokens": 23,
            "tool_uses": 1,
            "duration_ms": 50,
        },
    },)

    ledger = token_ledger(record, messages, reviewers)

    assert ledger["complete"] is True
    assert ledger["aggregate"]["total_tokens"] == 154
    assert [row["caller"] for row in ledger["rounds"]] == [
        "parent",
        "reviewer",
    ]
    assert ledger["terminal_result"]["is_error"] is True
    assert ledger["reviewer_attribution"][0]["total_tokens"] == 23


def test_token_ledger_thaws_frozen_nested_usage_for_json_artifacts() -> None:
    record = AgentCallRecord(
        run_id="run-1",
        role="quality_operator",
        model="test-model",
        prompt="prompt",
        prompt_version="v1",
        schema_version="v1",
        tool_version="v1",
        structured_output=None,
        tool_calls=(),
        usage=TokenUsage(),
        turns=1,
        observed_model_rounds=1,
        elapsed_ms=1,
        error=None,
        usage_complete=True,
    )
    frozen_usage = MappingProxyType({"input_tokens": 3})
    frozen_models = MappingProxyType(
        {"test-model": MappingProxyType({"inputTokens": 3})}
    )

    ledger = token_ledger(
        record,
        (
            MappingProxyType(
                {
                    "kind": "result",
                    "usage": frozen_usage,
                    "model_usage": frozen_models,
                }
            ),
        ),
        (),
    )

    assert json.loads(json.dumps(ledger))["terminal_result"]["model_usage"] == {
        "test-model": {"inputTokens": 3}
    }
