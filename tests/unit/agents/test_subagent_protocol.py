import json

import pytest

from manim_quality.agents._reviewer_values import reviewer_payload
from manim_quality.agents._subagent_protocol import (
    NativeSubagentProtocol,
    SubagentProtocolError,
)

REVIEWER = "math_geometry_reviewer"


def valid_result() -> str:
    return json.dumps(
        {
            "decision": "pass",
            "diagnosis": "No supported defect.",
            "issues": [],
            "coverage": {"diagrams": ["main"]},
            "confidence": 0.9,
        },
        separators=(",", ":"),
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0.95, 0.95),
        (95, 0.95),
        ("95%", 0.95),
        ("high", 0.9),
        ("medium", 0.6),
        ("low", 0.3),
    ],
)
def test_reviewer_confidence_accepts_common_equivalent_scales(
    raw, expected
) -> None:
    payload = json.loads(valid_result())
    payload["confidence"] = raw

    normalized = reviewer_payload(json.dumps(payload), SubagentProtocolError)

    assert normalized["confidence"] == expected


def test_reviewer_payload_ignores_extra_metadata() -> None:
    payload = json.loads(valid_result())
    payload["notes"] = "extra model metadata"
    payload["decision"] = "needs_repair"
    payload["issues"] = [
        {
            "type": "blocking",
            "target": "line AB",
            "evidence": ["source line"],
            "required_invariant": "AB remains aligned.",
            "repair_scope": "Solution.construct",
            "severity": "blocking",
        }
    ]

    normalized = reviewer_payload(json.dumps(payload), SubagentProtocolError)

    assert "notes" not in normalized
    assert "severity" not in normalized["issues"][0]
    assert normalized["issues"][0]["target"] == "line AB"


def sdk_result(
    result: str | None = None,
    *,
    agent_id: str = "agent-1",
) -> str:
    return (
        f"{result or valid_result()}\n"
        f"agentId: {agent_id} "
        f"(use SendMessage with to: '{agent_id}', summary: '<5-10 word recap>' "
        "to continue this agent)\n"
        "<usage>subagent_tokens: 6018\n"
        "tool_uses: 1\n"
        "duration_ms: 48086</usage>"
    )


def started() -> NativeSubagentProtocol:
    protocol = NativeSubagentProtocol((REVIEWER,))
    protocol.authorize(REVIEWER, "tool-1")
    protocol.start(REVIEWER, "agent-1")
    return protocol


def stopped() -> NativeSubagentProtocol:
    protocol = started()
    protocol.authorize_tool(
        agent_type=REVIEWER,
        agent_id="agent-1",
        tool_name="mcp__quality__read_solution",
    )
    protocol.stop(REVIEWER, "agent-1")
    return protocol


def test_protocol_requires_bound_identity_and_active_lifecycle() -> None:
    protocol = started()

    with pytest.raises(SubagentProtocolError, match="does not match"):
        protocol.authorize_tool(
            agent_type=REVIEWER,
            agent_id="forged-agent",
            tool_name="mcp__quality__read_solution",
        )
    with pytest.raises(SubagentProtocolError, match="started twice"):
        protocol.start(REVIEWER, "agent-2")

    protocol.authorize_tool(
        agent_type=REVIEWER,
        agent_id="agent-1",
        tool_name="mcp__quality__read_solution",
    )
    protocol.stop(REVIEWER, "agent-1")
    with pytest.raises(SubagentProtocolError, match="after stop"):
        protocol.authorize_tool(
            agent_type=REVIEWER,
            agent_id="agent-1",
            tool_name="mcp__quality__check_relation",
        )


def test_protocol_requires_stop_and_one_successful_json_result() -> None:
    protocol = started()
    with pytest.raises(SubagentProtocolError, match="before stop"):
        protocol.record_result(
            tool_use_id="tool-1",
            content=valid_result(),
            is_error=False,
            parent_tool_use_id=None,
        )

    protocol = stopped()
    with pytest.raises(SubagentProtocolError, match="error ToolResult"):
        protocol.record_result(
            tool_use_id="tool-1",
            content=valid_result(),
            is_error=True,
            parent_tool_use_id=None,
        )

    protocol = stopped()
    protocol.record_result(
        tool_use_id="tool-1",
        content="not-json",
        is_error=False,
        parent_tool_use_id=None,
    )
    assert protocol.results[0]["payload"]["decision"] == "needs_repair"


def test_protocol_requires_parent_consumption_and_rejects_duplicates() -> None:
    protocol = stopped()
    protocol.record_result(
        tool_use_id="tool-1",
        content=valid_result(),
        is_error=False,
        parent_tool_use_id=None,
    )

    with pytest.raises(SubagentProtocolError, match="duplicate"):
        protocol.record_result(
            tool_use_id="tool-1",
            content=valid_result(),
            is_error=False,
            parent_tool_use_id=None,
        )
    with pytest.raises(SubagentProtocolError, match="did not consume"):
        protocol.validate_complete()

    protocol.bind_parent_message("parent-next")
    protocol.validate_complete()
    assert protocol.results[0]["parent_next_message_id"] == "parent-next"


def test_protocol_strips_and_validates_sdk_agent_result_trailer() -> None:
    protocol = stopped()
    protocol.record_result(
        tool_use_id="tool-1",
        content=sdk_result(),
        is_error=False,
        parent_tool_use_id=None,
    )

    result = protocol.results[0]
    assert result["content"] == valid_result()
    assert result["sdk_metadata"] == {
        "agent_id": "agent-1",
        "subagent_tokens": 6018,
        "tool_uses": 1,
        "duration_ms": 48086,
    }


@pytest.mark.parametrize(
    ("content", "match"),
    [
        (sdk_result(agent_id="forged-agent"), "does not match"),
    ],
)
def test_protocol_rejects_forged_or_unknown_sdk_trailers(
    content: str,
    match: str,
) -> None:
    protocol = stopped()
    with pytest.raises(SubagentProtocolError, match=match):
        protocol.record_result(
            tool_use_id="tool-1",
            content=content,
            is_error=False,
            parent_tool_use_id=None,
        )


def test_protocol_preserves_malformed_issue_as_non_blocking_evidence() -> None:
    protocol = stopped()
    malformed = json.loads(valid_result())
    malformed["issues"] = [{"type": "logic"}]

    protocol.record_result(
        tool_use_id="tool-1",
        content=json.dumps(malformed),
        is_error=False,
        parent_tool_use_id=None,
    )

    payload = protocol.results[0]["payload"]
    assert payload["decision"] == "needs_repair"
    assert payload["issues"][0]["target"] == "Solution"
    assert "issue_target_defaulted" in payload["coverage"]["protocol_warnings"]

    protocol = stopped()
    detailed = json.loads(valid_result())
    detailed["diagnosis"] = "x" * 6_000
    protocol.record_result(
        tool_use_id="tool-1",
        content=json.dumps(detailed),
        is_error=False,
        parent_tool_use_id=None,
    )
    assert len(protocol.results[0]["payload"]["diagnosis"]) == 6_000

    protocol = stopped()
    oversized = json.loads(valid_result())
    oversized["diagnosis"] = "x" * 8_001
    with pytest.raises(SubagentProtocolError, match="8000"):
        protocol.record_result(
            tool_use_id="tool-1",
            content=json.dumps(oversized),
            is_error=False,
            parent_tool_use_id=None,
        )


def test_reviewer_json_survives_markdown_fences_and_prose() -> None:
    import json as _json

    from manim_quality.agents._subagent_protocol import _result_parts

    payload = _json.dumps(
        {
            "decision": "pass",
            "diagnosis": "clean",
            "issues": [],
            "coverage": {"scenes": 1},
            "confidence": 0.9,
        }
    )
    wrapped = f"Here is my review:\n```json\n{payload}\n```\n"
    reviewer_text, trailer = _result_parts(wrapped, expected_agent_id=None)

    assert _json.loads(reviewer_text)["decision"] == "pass"
    assert trailer is None


def test_reviewer_json_accepts_provider_tail_as_non_blocking_evidence() -> None:
    protocol = stopped()
    protocol.record_result(
        tool_use_id="tool-1",
        content=valid_result() + "\nprovider explanation\n</｜DSML｜tool_calls>",
        is_error=False,
        parent_tool_use_id=None,
    )
    assert protocol.results[0]["payload"]["decision"] == "pass"


def test_unstructured_reviewer_output_is_preserved_and_does_not_block() -> None:
    protocol = stopped()
    protocol.record_result(
        tool_use_id="tool-1",
        content='结论基本正确，但这里有 "未转义引号"。',
        is_error=False,
        parent_tool_use_id=None,
    )
    payload = protocol.results[0]["payload"]
    assert payload["decision"] == "needs_repair"
    assert "未转义引号" in payload["diagnosis"]
    assert payload["coverage"]["protocol_warnings"] == [
        "unstructured_output_preserved"
    ]


def test_reviewer_json_is_found_after_a_schema_example_block() -> None:
    import json as _json

    from manim_quality.agents._subagent_protocol import _result_parts

    example = '{"decision": "..."}'
    real = _json.dumps(
        {
            "decision": "needs_repair",
            "diagnosis": "angle mismatch",
            "issues": [],
            "coverage": {"scenes": 2},
            "confidence": 0.8,
        }
    )
    wrapped = (
        "Schema example:\n```json\n" + example + "\n```\n"
        "My actual review:\n```json\n" + real + "\n```\n"
    )
    reviewer_text, trailer = _result_parts(wrapped, expected_agent_id=None)

    assert _json.loads(reviewer_text)["diagnosis"] == "angle mismatch"
    assert trailer is None


def test_prose_braces_before_reviewer_json_do_not_break_extraction() -> None:
    import json as _json

    from manim_quality.agents._subagent_protocol import _result_parts

    real = _json.dumps(
        {
            "decision": "pass",
            "diagnosis": "ok",
            "issues": [],
            "coverage": {},
            "confidence": 0.7,
        }
    )
    wrapped = "The set {x} and \\frac{a}{b} appear fine.\n" + real
    reviewer_text, _ = _result_parts(wrapped, expected_agent_id=None)

    assert _json.loads(reviewer_text)["decision"] == "pass"
