"""Token ledgers shared by complete and interrupted artifact writers."""

from collections.abc import Mapping

from manim_quality.contracts._json_values import thaw_json_object


def _plain_mapping(value: object) -> object:
    return thaw_json_object(value) if isinstance(value, Mapping) else value


def usage_record(value) -> dict[str, int]:
    return {
        "input_tokens": value.input_tokens,
        "output_tokens": value.output_tokens,
        "cache_read_tokens": value.cache_read_tokens,
        "cache_write_tokens": value.cache_write_tokens,
        "total_tokens": value.total_tokens,
    }


def reviewer_tokens(subagent_results) -> int:
    total = 0
    for item in subagent_results:
        metadata = item.get("sdk_metadata")
        if isinstance(metadata, Mapping):
            value = metadata.get("subagent_tokens")
            if isinstance(value, int) and not isinstance(value, bool):
                total += value
    return total


def token_ledger(record, sdk_messages, subagent_results) -> dict[str, object]:
    """Persist aggregate, per-message, and Reviewer attribution in one ledger."""

    rounds = []
    terminal = None
    for message in sdk_messages:
        kind = message.get("kind")
        if kind == "assistant":
            rounds.append({
                "message_id": message.get("message_id"),
                "caller": (
                    "reviewer"
                    if isinstance(message.get("parent_tool_use_id"), str)
                    else "parent"
                ),
                "parent_tool_use_id": message.get("parent_tool_use_id"),
                "model": message.get("model"),
                "usage": _plain_mapping(message.get("usage")),
            })
        elif kind == "result":
            terminal = {
                "subtype": message.get("subtype"),
                "is_error": message.get("is_error"),
                "num_turns": message.get("num_turns"),
                "session_id": message.get("session_id"),
                "usage": _plain_mapping(message.get("usage")),
                "model_usage": _plain_mapping(message.get("model_usage")),
            }
    reviewers = []
    for item in subagent_results:
        metadata = item.get("sdk_metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        reviewers.append({
            "agent_id": item.get("agent_id"),
            "agent_type": item.get("agent_type"),
            "total_tokens": metadata.get("subagent_tokens"),
            "tool_uses": metadata.get("tool_uses"),
            "duration_ms": metadata.get("duration_ms"),
        })
    return {
        "schema_version": "manim-quality.token-ledger.v1",
        "complete": record.usage_complete,
        "aggregate": usage_record(record.usage),
        "rounds": rounds,
        "terminal_result": terminal,
        "reviewer_attribution": reviewers,
    }
