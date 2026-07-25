from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from .settings import mask_secret


DEFAULT_ALLOWED_TOOLS = ["Read", "Edit"]
DEFAULT_DISALLOWED_TOOLS = ["Bash", "Write"]
EDITOR_SYSTEM_PROMPT = "\n".join(
    [
        "You are a terse code editor for one local Manim repair.",
        "Use only the allowed tools needed to apply the requested edit.",
        "Do not narrate, brainstorm, start a new task, or read files after a successful final edit.",
        "When all requested edits are applied, respond with exactly: DONE",
    ]
)


@dataclass(frozen=True)
class ClaudeSdkRepairConfig:
    base_url: str
    api_key: str
    model: str
    cwd: str | None = None
    max_turns: int = 6
    max_budget_usd: float | None = 0.75
    timeout_sec: int = 300
    allowed_tools: tuple[str, ...] = ("Read", "Edit")
    disallowed_tools: tuple[str, ...] = ("Bash", "Write")
    permission_mode: str = "acceptEdits"

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @property
    def masked_api_key(self) -> str:
        return mask_secret(self.api_key)

    def __repr__(self) -> str:
        return (
            "ClaudeSdkRepairConfig("
            f"base_url={self.base_url!r}, api_key={self.masked_api_key!r}, "
            f"model={self.model!r}, cwd={self.cwd!r}, max_turns={self.max_turns!r})"
        )


def build_sdk_env(config: ClaudeSdkRepairConfig) -> dict[str, str]:
    return {
        "ANTHROPIC_BASE_URL": config.base_url,
        "ANTHROPIC_API_KEY": config.api_key,
        "ANTHROPIC_AUTH_TOKEN": config.api_key,
    }


def sdk_permission_summary(config: ClaudeSdkRepairConfig) -> dict[str, Any]:
    return {
        "cwd": config.cwd,
        "model": config.model,
        "base_url": config.base_url,
        "api_key": config.masked_api_key,
        "allowed_tools": list(config.allowed_tools),
        "disallowed_tools": list(config.disallowed_tools),
        "permission_mode": config.permission_mode,
        "max_turns": config.max_turns,
        "max_budget_usd": config.max_budget_usd,
    }


async def run_sdk_repair(
    *,
    prompt: str,
    config: ClaudeSdkRepairConfig,
    query_func: Callable[..., AsyncIterator[Any]] | None = None,
) -> dict[str, Any]:
    query, options = _build_query(config, query_func=query_func)
    messages: list[Any] = []
    started = time.monotonic()
    error: dict[str, str] | None = None

    async def _collect() -> None:
        async for message in query(prompt=prompt, options=options):
            messages.append(message)

    try:
        await asyncio.wait_for(_collect(), timeout=config.timeout_sec)
    except Exception as exc:  # noqa: BLE001 - runner boundary returns structured evidence
        error = _classify_sdk_exception(exc, messages)

    return {
        "ok": error is None,
        "error": error,
        "elapsed_sec": round(time.monotonic() - started, 3),
        "usage": extract_usage(messages),
        "messages": [_to_jsonable(message) for message in messages],
        "permission_summary": sdk_permission_summary(config),
    }


def _classify_sdk_exception(exc: Exception, messages: list[Any]) -> dict[str, Any]:
    api_error = _last_api_error(messages)
    if api_error is not None:
        return {
            "type": "sdk_api_unavailable" if api_error["status"] == 503 else "sdk_api_error",
            "status": api_error["status"],
            "message": api_error["message"],
            "exception_type": type(exc).__name__,
        }
    return {"type": type(exc).__name__, "message": str(exc)}


def _last_api_error(messages: list[Any]) -> dict[str, Any] | None:
    for message in reversed(messages):
        status = _get(message, "api_error_status")
        result = _get(message, "result")
        data = _get(message, "data")
        if status is None and data is not None:
            status = _get(data, "api_error_status") or _get(data, "error_status")
            result = result or _get(data, "result") or _get(data, "error")
        if status is None:
            continue
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            continue
        return {"status": status_int, "message": str(result or "")}
    return None


def _build_query(
    config: ClaudeSdkRepairConfig,
    *,
    query_func: Callable[..., AsyncIterator[Any]] | None,
) -> tuple[Callable[..., AsyncIterator[Any]], Any]:
    from claude_agent_sdk import ClaudeAgentOptions

    options = ClaudeAgentOptions(
        cwd=config.cwd,
        model=config.model,
        tools=list(config.allowed_tools),
        allowed_tools=list(config.allowed_tools),
        system_prompt=EDITOR_SYSTEM_PROMPT,
        disallowed_tools=list(config.disallowed_tools),
        permission_mode=config.permission_mode,
        max_turns=config.max_turns,
        max_budget_usd=config.max_budget_usd,
        mcp_servers={},
        strict_mcp_config=True,
        setting_sources=[],
        skills=[],
        plugins=[],
        thinking={"type": "disabled"},
        effort="low",
        env=build_sdk_env(config),
    )
    if query_func is not None:
        return query_func, options
    from claude_agent_sdk import query

    return query, options


def extract_usage(messages: list[Any]) -> dict[str, Any]:
    input_tokens = 0
    output_tokens = 0
    total_cost_usd = 0.0
    tool_calls: dict[str, int] = {}
    for message in messages:
        usage = _get(message, "usage")
        if usage:
            input_tokens += _usage_int(usage, "input_tokens")
            input_tokens += _usage_int(usage, "cache_creation_input_tokens")
            input_tokens += _usage_int(usage, "cache_read_input_tokens")
            output_tokens += _usage_int(usage, "output_tokens")
        total_cost_usd += float(_get(message, "total_cost_usd") or 0.0)
        for block in _get(message, "content") or []:
            name = _get(block, "name")
            block_type = _get(block, "type")
            if name or block_type == "tool_use":
                key = str(name or "unknown")
                tool_calls[key] = tool_calls.get(key, 0) + 1
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "total_cost_usd": round(total_cost_usd, 6),
        "tool_calls": tool_calls,
        "tool_step_count": sum(tool_calls.values()),
    }


def write_agent_result(path: Path, result: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _usage_int(usage: Any, key: str) -> int:
    value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _get(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _to_jsonable(vars(value))
    return repr(value)
