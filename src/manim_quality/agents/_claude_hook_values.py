"""Pure value conversion helpers for Claude SDK hook messages."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ResultMessage, UserMessage

from .usage import TokenUsage


class ClaudeSdkProtocolError(RuntimeError):
    pass


def parse_token_usage(value: object) -> TokenUsage:
    if not isinstance(value, Mapping):
        raise ClaudeSdkProtocolError("assistant usage is required for every turn")
    return TokenUsage(
        input_tokens=_usage_count(value, "input_tokens"),
        output_tokens=_usage_count(value, "output_tokens"),
        cache_read_tokens=_usage_count(value, "cache_read_input_tokens"),
        cache_write_tokens=_usage_count(value, "cache_creation_input_tokens"),
    )


def usage_delta(previous: TokenUsage, current: TokenUsage) -> TokenUsage:
    return TokenUsage(
        input_tokens=max(0, current.input_tokens - previous.input_tokens),
        output_tokens=max(0, current.output_tokens - previous.output_tokens),
        cache_read_tokens=max(
            0,
            current.cache_read_tokens - previous.cache_read_tokens,
        ),
        cache_write_tokens=max(
            0,
            current.cache_write_tokens - previous.cache_write_tokens,
        ),
    )


def normalize_sdk_input(value: object, workspace: str) -> object:
    if not isinstance(value, Mapping):
        return value
    path = value.get("file_path")
    if not isinstance(path, str):
        return value
    portable = path.replace("\\", "/")
    prefix = "/workspace/"
    if portable.startswith("//"):
        return value
    if portable.casefold().startswith(prefix):
        relative = portable[len(prefix) :]
    elif portable.startswith("/"):
        relative = portable[1:]
    else:
        return value
    normalized = dict(value)
    normalized["file_path"] = str(Path(workspace) / relative)
    return normalized


def message_record(
    message: AssistantMessage | UserMessage | ResultMessage,
) -> dict[str, object]:
    if isinstance(message, AssistantMessage):
        return {
            "kind": "assistant",
            "message_id": message.message_id,
            "parent_tool_use_id": message.parent_tool_use_id,
            "model": message.model,
            "stop_reason": message.stop_reason,
            "error": _json_safe(message.error),
            "usage": _json_safe(message.usage),
            "content": _json_safe(message.content),
        }
    if isinstance(message, UserMessage):
        return {
            "kind": "user",
            "uuid": message.uuid,
            "parent_tool_use_id": message.parent_tool_use_id,
            "tool_use_result": _json_safe(message.tool_use_result),
            "content": _json_safe(message.content),
        }
    return {
        "kind": "result",
        "subtype": message.subtype,
        "is_error": message.is_error,
        "num_turns": message.num_turns,
        "session_id": message.session_id,
        "stop_reason": message.stop_reason,
        "duration_ms": message.duration_ms,
        "duration_api_ms": message.duration_api_ms,
        "usage": _json_safe(message.usage),
        "model_usage": _json_safe(message.model_usage),
        "structured_output": _json_safe(message.structured_output),
        "errors": _json_safe(message.errors),
    }


def _usage_count(value: Mapping[object, object], key: str) -> int:
    count = value.get(key, 0)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ClaudeSdkProtocolError(f"invalid SDK usage field: {key}")
    return count


def _json_safe(value: object) -> object:
    if dataclasses.is_dataclass(value):
        value = dataclasses.asdict(value)
    elif isinstance(value, list):
        value = [_json_safe(item) for item in value]
    elif isinstance(value, tuple):
        value = [_json_safe(item) for item in value]
    elif isinstance(value, Mapping):
        value = {str(key): _json_safe(item) for key, item in value.items()}
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return str(value)
