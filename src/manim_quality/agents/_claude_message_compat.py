"""Compatibility for Anthropic relays that omit thinking signatures.

Claude Code has already consumed the provider response before the Python SDK
parses the CLI event.  Some Anthropic-compatible relays occasionally emit an
unsigned ``thinking`` block in that event.  The Python SDK rejects the whole
assistant message, which aborts an otherwise valid tool session.

Unsigned reasoning is not required by the quality runtime, so drop only that
untrusted block and preserve text, tool calls, usage, and result messages.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize_assistant_message(data: dict[str, Any]) -> dict[str, Any]:
    """Return an SDK event without unsigned thinking blocks."""

    if data.get("type") != "assistant":
        return data
    message = data.get("message")
    if not isinstance(message, dict):
        return data
    content = message.get("content")
    if not isinstance(content, list):
        return data
    if not any(_is_unsigned_thinking(block) for block in content):
        return data

    normalized = deepcopy(data)
    normalized["message"]["content"] = [
        block
        for block in normalized["message"]["content"]
        if not _is_unsigned_thinking(block)
    ]
    return normalized


def install_claude_sdk_message_compat() -> None:
    """Install the narrow parser compatibility once per process."""

    from claude_agent_sdk._internal import client as internal_client
    from claude_agent_sdk._internal import message_parser

    current = message_parser.parse_message
    if getattr(current, "_manim_quality_unsigned_thinking_compat", False):
        return

    def parse_message(data: dict[str, Any]):
        return current(normalize_assistant_message(data))

    parse_message._manim_quality_unsigned_thinking_compat = True
    message_parser.parse_message = parse_message
    internal_client.parse_message = parse_message


def _is_unsigned_thinking(block: object) -> bool:
    if not isinstance(block, dict) or block.get("type") != "thinking":
        return False
    signature = block.get("signature")
    return not isinstance(signature, str) or not signature.strip()
