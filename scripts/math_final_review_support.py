from __future__ import annotations

from manim_quality.contracts._json_values import thaw_json_object


def record_payload(record) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "run_id": record.run_id,
        "model": record.model,
        "structured_output": (
            thaw_json_object(record.structured_output)
            if record.structured_output is not None
            else None
        ),
        "tool_calls": [
            {
                "name": item.name,
                "input": thaw_json_object(item.input),
                "allowed": item.allowed,
                "error": item.error,
                "result_status": item.result_status,
                "caller": item.caller,
                "agent_id": item.agent_id,
                "agent_type": item.agent_type,
            }
            for item in record.tool_calls
        ],
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_read_tokens": record.usage.cache_read_tokens,
            "cache_write_tokens": record.usage.cache_write_tokens,
            "total_tokens": record.usage.total_tokens,
        },
        "turns": record.turns,
        "elapsed_ms": record.elapsed_ms,
        "error": record.error,
    }
