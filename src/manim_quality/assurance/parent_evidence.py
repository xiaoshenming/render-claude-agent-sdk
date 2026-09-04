"""Persist final Parent evidence on success and failure before workspace cleanup."""

import json
from pathlib import Path

from manim_quality.contracts._json_values import thaw_json_object


def record_parent_attempt(output_dir: Path, attempt, record, messages=(), subagents=()):
    output_dir.mkdir(parents=True, exist_ok=True)
    usage = record.usage
    payload = {
        "attempt": attempt, "run_id": record.run_id,
        "status": "failed" if record.error else "succeeded",
        "error": record.error, "elapsed_ms": record.elapsed_ms,
        "turns": record.turns, "tool_calls": len(record.tool_calls),
        "usage": {
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
            "cache_read_tokens": usage.cache_read_tokens,
            "cache_write_tokens": usage.cache_write_tokens,
        },
    }
    _append(output_dir / "parent-attempts.jsonl", payload)
    for message in messages:
        _append(output_dir / "parent-sdk-messages.jsonl",
                {"attempt": attempt, "message": thaw_json_object(message)})
    for value in subagents:
        _append(output_dir / "parent-subagent-results.jsonl",
                {"attempt": attempt, "result": thaw_json_object(value)})
    for tool in record.tool_calls:
        _append(output_dir / "parent-tool-results.jsonl", {
            "attempt": attempt, "name": tool.name, "call_id": tool.call_id,
            "allowed": tool.allowed, "error": tool.error,
            "result_status": tool.result_status,
            "started_at_ms": tool.started_at_ms, "finished_at_ms": tool.finished_at_ms,
        })


def _append(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
