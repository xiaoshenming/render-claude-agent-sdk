from __future__ import annotations

import ast
import json
import os
from pathlib import Path

from manim_quality.contracts._json_values import thaw_json_object


def authoritative_problem(source: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(
            isinstance(target, ast.Name)
            and target.id == "AUTHORITATIVE_PROBLEM_TEXT"
            for target in targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and value.strip():
                return value.strip()
    raise ValueError("AUTHORITATIVE_PROBLEM_TEXT missing")


def provider_env() -> dict[str, str]:
    names = ("ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    result = {name: os.environ[name] for name in names if os.environ.get(name)}
    settings = Path("/home/ming/.claude/settings.json")
    if settings.is_file():
        configured = json.loads(settings.read_text(encoding="utf-8")).get("env", {})
        for name in names:
            if not result.get(name) and configured.get(name):
                result[name] = configured[name]
    if not result.get("ANTHROPIC_API_KEY") and not result.get(
        "ANTHROPIC_AUTH_TOKEN"
    ):
        raise RuntimeError("missing provider credentials")
    return result


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
