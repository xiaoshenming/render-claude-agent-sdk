"""Immutable usage and transcript records for every Agent call."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from manim_quality.contracts._json_values import freeze_json_object

if TYPE_CHECKING:
    from ._runtime_models import AgentRunRequest


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __post_init__(self) -> None:
        for name in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
        ):
            _require_non_negative_int(getattr(self, name), name)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    @property
    def input_accounted_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens

    def plus(self, other: TokenUsage) -> TokenUsage:
        if not isinstance(other, TokenUsage):
            raise TypeError("other must be TokenUsage")
        return TokenUsage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            cache_read_tokens=self.cache_read_tokens + other.cache_read_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True, slots=True)
class ToolCallRecord:
    name: str
    input: Mapping[str, object]
    allowed: bool
    error: str | None = None
    result_status: str | None = None
    result_hash: str | None = None
    caller: str = "parent"
    agent_id: str | None = None
    agent_type: str | None = None
    call_id: str | None = None
    started_at_ms: int | None = None
    finished_at_ms: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:  # noqa: C901 - validates one immutable record
        _require_text(self.name, "name")
        object.__setattr__(self, "input", freeze_json_object(self.input, "input"))
        if not isinstance(self.allowed, bool):
            raise TypeError("allowed must be bool")
        if self.error is not None:
            _require_text(self.error, "error")
        if self.result_status is not None and self.result_status not in {"ok", "error"}:
            raise ValueError("result_status must be ok, error, or None")
        if self.result_hash is not None:
            _require_text(self.result_hash, "result_hash")
        if (self.result_status is None) != (self.result_hash is None):
            raise ValueError("tool result status and hash must be recorded together")
        _require_text(self.caller, "caller")
        if self.agent_id is not None:
            _require_text(self.agent_id, "agent_id")
        if self.agent_type is not None:
            _require_text(self.agent_type, "agent_type")
        if self.call_id is not None:
            _require_text(self.call_id, "call_id")
        for name in ("started_at_ms", "finished_at_ms", "duration_ms"):
            value = getattr(self, name)
            if value is not None:
                _require_non_negative_int(value, name)
        if self.finished_at_ms is not None and self.started_at_ms is None:
            raise ValueError("finished_at_ms requires started_at_ms")
        if self.duration_ms is not None and self.finished_at_ms is None:
            raise ValueError("duration_ms requires finished_at_ms")


@dataclass(frozen=True, slots=True)
class AgentCallRecord:
    run_id: str
    role: str
    model: str
    prompt: str
    prompt_version: str
    schema_version: str
    tool_version: str
    structured_output: Mapping[str, object] | None
    tool_calls: Sequence[ToolCallRecord]
    usage: TokenUsage
    turns: int
    observed_model_rounds: int
    elapsed_ms: int
    error: str | None
    external_tool_ms: int = 0
    usage_complete: bool = True

    def __post_init__(self) -> None:
        for name in (
            "run_id",
            "role",
            "model",
            "prompt",
            "prompt_version",
            "schema_version",
            "tool_version",
        ):
            _require_text(getattr(self, name), name)
        if self.structured_output is not None:
            object.__setattr__(
                self,
                "structured_output",
                freeze_json_object(self.structured_output, "structured_output"),
            )
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        if not isinstance(self.usage, TokenUsage):
            raise TypeError("usage must be TokenUsage")
        _require_non_negative_int(self.turns, "turns")
        _require_non_negative_int(self.observed_model_rounds, "observed_model_rounds")
        _require_non_negative_int(self.elapsed_ms, "elapsed_ms")
        _require_non_negative_int(self.external_tool_ms, "external_tool_ms")
        if not isinstance(self.usage_complete, bool):
            raise TypeError("usage_complete must be bool")
        if self.error is not None:
            _require_text(self.error, "error")


@runtime_checkable
class UsageSink(Protocol):
    def save(self, record: AgentCallRecord) -> None: ...


@dataclass(frozen=True, slots=True)
class JobUsageReceipt:
    job_id: str
    calls: int
    usage: TokenUsage
    elapsed_ms: int
    external_tool_ms: int
    usage_complete: bool
    record_hashes: tuple[str, ...]


def aggregate_job_usage(
    job_id: str,
    records: Sequence[AgentCallRecord],
) -> JobUsageReceipt:
    usage = TokenUsage()
    for record in records:
        usage = usage.plus(record.usage)
    return JobUsageReceipt(
        job_id=job_id,
        calls=len(records),
        usage=usage,
        elapsed_ms=sum(record.elapsed_ms for record in records),
        external_tool_ms=sum(record.external_tool_ms for record in records),
        usage_complete=all(record.usage_complete for record in records),
        record_hashes=tuple(_record_hash(record) for record in records),
    )


class JsonlUsageLedger(UsageSink):
    """Append-only cross-process ledger; one fsync'd record per completed call."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def save(self, record: AgentCallRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = _record_payload(record)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())


def _record_payload(record: AgentCallRecord) -> dict[str, object]:
    return {
        "run_id": record.run_id,
        "role": record.role,
        "model": record.model,
        "prompt_version": record.prompt_version,
        "schema_version": record.schema_version,
        "tool_version": record.tool_version,
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_read_tokens": record.usage.cache_read_tokens,
            "cache_write_tokens": record.usage.cache_write_tokens,
        },
        "turns": record.turns,
        "observed_model_rounds": record.observed_model_rounds,
        "elapsed_ms": record.elapsed_ms,
        "external_tool_ms": record.external_tool_ms,
        "usage_complete": record.usage_complete,
        "tool_calls": [
            {
                "name": call.name,
                "caller": call.caller,
                "agent_id": call.agent_id,
                "duration_ms": call.duration_ms,
                "result_status": call.result_status,
            }
            for call in record.tool_calls
        ],
        "error": record.error,
    }


def _record_hash(record: AgentCallRecord) -> str:
    raw = json.dumps(_record_payload(record), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def recordable_tool_input(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        try:
            return freeze_json_object(value, "tool_input")
        except (TypeError, ValueError):
            pass
    return {"unrecordable_input_type": type(value).__name__}


def build_agent_call_record(
    *,
    request: AgentRunRequest,
    output: Mapping[str, object] | None,
    tool_calls: Sequence[ToolCallRecord],
    usage: TokenUsage,
    turns: int,
    observed_model_rounds: int,
    elapsed_ms: int,
    error: str | None,
    external_tool_ms: int = 0,
    usage_complete: bool = True,
) -> AgentCallRecord:
    profile = request.profile
    return AgentCallRecord(
        run_id=request.run_id,
        role=profile.role.value,
        model=profile.model,
        prompt=request.prompt,
        prompt_version=profile.prompt_version,
        schema_version=profile.schema_version,
        tool_version=profile.tool_version,
        structured_output=output,
        tool_calls=tool_calls,
        usage=usage,
        turns=turns,
        observed_model_rounds=observed_model_rounds,
        elapsed_ms=elapsed_ms,
        error=error,
        external_tool_ms=external_tool_ms,
        usage_complete=usage_complete,
    )


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value
