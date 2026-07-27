"""Token ledgers shared by complete and interrupted artifact writers."""

from collections.abc import Mapping


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
