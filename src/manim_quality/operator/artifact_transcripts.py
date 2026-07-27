"""Derived audit streams for SDK messages and tool results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def reviewer_messages(
    messages: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    """Keep every message emitted inside a native Reviewer context."""

    return [
        message
        for message in messages
        if isinstance(message.get("parent_tool_use_id"), str)
    ]


def tool_results(
    messages: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Extract full ToolResult payloads instead of retaining hashes alone."""

    results: list[dict[str, object]] = []
    for message in messages:
        if message.get("kind") != "user":
            continue
        content = message.get("content")
        blocks = content if isinstance(content, list) else []
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            tool_use_id = block.get("tool_use_id")
            if not isinstance(tool_use_id, str):
                continue
            results.append({
                "tool_use_id": tool_use_id,
                "parent_tool_use_id": message.get("parent_tool_use_id"),
                "is_error": bool(block.get("is_error")),
                "content": block.get("content"),
            })
    return results
