"""Claude SDK stream consumption and transcript records."""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from typing import Any


class SDKResultError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        tokens: int,
        cost: float,
        tool_calls: dict[str, int],
        usage: dict[str, int],
        records: list[dict[str, Any]],
        final_text: str = "",
    ) -> None:
        super().__init__(message)
        self.tokens = tokens
        self.cost = cost
        self.tool_calls = tool_calls
        self.usage = usage
        self.records = records
        self.final_text = final_text


async def _consume_query(
    sdk: Any, prompt: str, options: Any
) -> tuple[int, float, dict[str, int], list[dict[str, Any]], dict[str, int], str]:
    tokens = 0
    cost = 0.0
    tool_calls: dict[str, int] = {}
    records: list[dict[str, Any]] = []
    usage_totals = _empty_usage()
    result_error: str | None = None
    final_text = ""
    try:
        async for msg in sdk.query(prompt=prompt, options=options):
            records.append(_message_record(sdk, msg))
            if isinstance(msg, sdk.AssistantMessage):
                texts = [b.text for b in msg.content if isinstance(b, sdk.TextBlock)]
                if texts:
                    final_text = "".join(texts).strip()
                for block in msg.content:
                    if isinstance(block, sdk.ToolUseBlock):
                        tool_calls[block.name] = tool_calls.get(block.name, 0) + 1
            if isinstance(msg, sdk.ResultMessage):
                usage = msg.usage or {}
                _accumulate_usage(usage_totals, usage)
                tokens += int(_usage_value(usage, "input_tokens")) + int(_usage_value(usage, "output_tokens"))
                if msg.total_cost_usd:
                    cost += float(msg.total_cost_usd)
                if msg.is_error:
                    result_error = _result_error_text(msg)
    except Exception as exc:
        error = result_error or f"claude_sdk_exception:{exc}"
        raise SDKResultError(
            error,
            tokens=tokens,
            cost=cost,
            tool_calls=tool_calls,
            usage=usage_totals,
            records=records,
            final_text=final_text,
        ) from exc
    if result_error:
        raise SDKResultError(
            result_error,
            tokens=tokens,
            cost=cost,
            tool_calls=tool_calls,
            usage=usage_totals,
            records=records,
            final_text=final_text,
        )
    return tokens, cost, tool_calls, records, usage_totals, final_text


def _result_error_text(msg: Any) -> str:
    errors = getattr(msg, "errors", None)
    detail = "; ".join(str(item) for item in errors) if errors else str(getattr(msg, "result", None) or getattr(msg, "subtype", None) or "unknown")
    status = getattr(msg, "api_error_status", None)
    return f"claude_sdk_result_error:http_{status}:{detail}" if status else f"claude_sdk_result_error:{detail}"


def _message_record(sdk: Any, msg: Any) -> dict[str, Any]:
    if isinstance(msg, sdk.AssistantMessage):
        texts = [b.text for b in msg.content if isinstance(b, sdk.TextBlock)]
        tool_blocks = [b for b in msg.content if isinstance(b, sdk.ToolUseBlock)]
        return {
            "type": "assistant",
            "text": "".join(texts),
            "tools": [b.name for b in tool_blocks],
            "tool_calls": [_tool_use_record(block) for block in tool_blocks],
            "usage": msg.usage,
        }
    if isinstance(msg, sdk.ResultMessage):
        return {"type": "result", "num_turns": msg.num_turns, "usage": msg.usage, "is_error": msg.is_error}
    if isinstance(msg, sdk.UserMessage):
        if isinstance(msg.content, str):
            return {"type": "user", "content": _preview(msg.content)}
        return {"type": "user", "content": "<blocks>", "tool_results": _tool_result_records(sdk, msg.content)}
    return {"type": type(msg).__name__}


def _empty_usage() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def _accumulate_usage(total: dict[str, int], usage: dict[str, Any]) -> None:
    for key in list(total):
        total[key] += int(_usage_value(usage, key))


def _usage_value(usage: dict[str, Any], snake_key: str) -> int:
    value = usage.get(snake_key)
    if value is None:
        value = usage.get(_camel_key(snake_key), 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _camel_key(snake_key: str) -> str:
    parts = snake_key.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _tool_use_record(block: Any) -> dict[str, Any]:
    name = str(getattr(block, "name", ""))
    payload = getattr(block, "input", None) if isinstance(getattr(block, "input", None), dict) else {}
    record: dict[str, Any] = {"name": name}
    if name == "Read":
        record["file_path"] = payload.get("file_path") or payload.get("filePath")
    elif name == "Edit":
        record["file_path"] = payload.get("file_path") or payload.get("filePath")
        record["old_string_length"] = len(str(payload.get("old_string", "")))
        record["new_string_length"] = len(str(payload.get("new_string", "")))
        record["replace_all"] = bool(payload.get("replace_all", False))
    else:
        record["input_keys"] = sorted(str(key) for key in payload)
    return record


def _tool_result_records(sdk: Any, blocks: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for block in blocks:
        if isinstance(block, sdk.ToolResultBlock):
            records.append({"tool_use_id": getattr(block, "tool_use_id", None), "is_error": getattr(block, "is_error", None), "content_preview": _preview(getattr(block, "content", None))})
    return records


def _preview(value: Any, limit: int = 800) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _write_transcript(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def _run_coro(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, Any] = {}

    def _target() -> None:
        box["value"] = asyncio.run(coro)

    thread = threading.Thread(target=_target)
    thread.start()
    thread.join()
    return box["value"]
