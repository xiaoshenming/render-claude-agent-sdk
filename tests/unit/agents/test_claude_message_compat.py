from claude_agent_sdk import AssistantMessage
from claude_agent_sdk._internal import client as internal_client
from claude_agent_sdk._internal import message_parser

from manim_quality.agents._claude_message_compat import (
    install_claude_sdk_message_compat,
    normalize_assistant_message,
)


def _assistant(content: list[dict]) -> dict:
    return {
        "type": "assistant",
        "message": {
            "content": content,
            "model": "gpt-compatible",
            "usage": {},
        },
    }


def test_normalizer_drops_only_unsigned_thinking() -> None:
    event = _assistant([
        {"type": "thinking", "thinking": "unsigned"},
        {"type": "text", "text": "keep me"},
        {
            "type": "thinking",
            "thinking": "signed",
            "signature": "verified-signature",
        },
    ])

    normalized = normalize_assistant_message(event)

    assert event["message"]["content"][0]["thinking"] == "unsigned"
    assert normalized["message"]["content"] == [
        {"type": "text", "text": "keep me"},
        {
            "type": "thinking",
            "thinking": "signed",
            "signature": "verified-signature",
        },
    ]


def test_installed_parser_accepts_relay_message_without_signature() -> None:
    install_claude_sdk_message_compat()

    parsed = message_parser.parse_message(
        _assistant([
            {"type": "thinking", "thinking": "relay omitted signature"},
            {
                "type": "tool_use",
                "id": "tool-1",
                "name": "read_solution",
                "input": {},
            },
        ])
    )

    assert isinstance(parsed, AssistantMessage)
    assert len(parsed.content) == 1
    assert parsed.content[0].name == "read_solution"
    assert internal_client.parse_message is message_parser.parse_message
