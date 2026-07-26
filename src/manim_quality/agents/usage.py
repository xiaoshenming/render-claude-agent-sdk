"""Immutable usage and transcript records for every Agent call."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
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

    def __post_init__(self) -> None:
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
