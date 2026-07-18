"""Immutable request and result models for the Agent runtime boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from manim_quality.contracts._json_values import freeze_json_object

from .profile import AgentProfile
from .read_tools import ReadonlyToolGrant
from .tool_policy import ToolInputPolicy
from .usage import AgentCallRecord


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    run_id: str
    profile: AgentProfile
    prompt: str
    output_schema: Mapping[str, object]
    workspace: Path
    readable_paths: Sequence[Path]
    editable_paths: Sequence[Path]
    context_bytes: int
    estimated_input_tokens: int
    reserved_output_tokens: int
    reserved_cache_read_tokens: int
    reserved_cache_write_tokens: int
    output_validator: Callable[[Mapping[str, object]], None] | None = None
    read_tools: Sequence[ReadonlyToolGrant] = ()
    tool_policies: Mapping[str, ToolInputPolicy] | None = None

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        if not isinstance(self.profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        _require_text(self.prompt, "prompt")
        object.__setattr__(
            self,
            "output_schema",
            freeze_json_object(self.output_schema, "output_schema"),
        )
        object.__setattr__(self, "workspace", Path(self.workspace))
        object.__setattr__(self, "readable_paths", tuple(self.readable_paths))
        object.__setattr__(self, "editable_paths", tuple(self.editable_paths))
        for name in (
            "context_bytes",
            "estimated_input_tokens",
            "reserved_output_tokens",
            "reserved_cache_read_tokens",
            "reserved_cache_write_tokens",
        ):
            _require_count(getattr(self, name), name)
        if self.output_validator is not None and not callable(self.output_validator):
            raise TypeError("output_validator must be callable or None")
        object.__setattr__(self, "read_tools", tuple(self.read_tools))
        if not all(isinstance(item, ReadonlyToolGrant) for item in self.read_tools):
            raise TypeError("read_tools must contain ReadonlyToolGrant values")
        policies = dict(self.tool_policies or {})
        if any(
            not isinstance(name, str) or not isinstance(policy, ToolInputPolicy)
            for name, policy in policies.items()
        ):
            raise TypeError("tool_policies must map names to ToolInputPolicy values")
        object.__setattr__(self, "tool_policies", MappingProxyType(policies))


@dataclass(frozen=True, slots=True)
class BackendRequest:
    prompt: str
    output_schema: Mapping[str, object]
    profile: AgentProfile
    workspace: str
    readable_paths: tuple[str, ...]
    editable_paths: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    read_tools: tuple[ReadonlyToolGrant, ...]
    max_turns: int
    max_tool_calls: int
    estimated_input_tokens: int
    reserved_output_tokens: int
    reserved_cache_read_tokens: int
    reserved_cache_write_tokens: int
    timeout_ms: int


@dataclass(frozen=True, slots=True)
class BackendResult:
    structured_output: Mapping[str, object]
    _control_token: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "structured_output",
            freeze_json_object(self.structured_output, "structured_output"),
        )


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    structured_output: Mapping[str, object]
    record: AgentCallRecord


class AgentRunFailed(RuntimeError):
    def __init__(self, record: AgentCallRecord) -> None:
        self.record = record
        super().__init__(record.error or "Agent run failed")


class RuntimeProtocolError(RuntimeError):
    pass


class OutputRejected(RuntimeError):
    pass


class CorrectableOutputError(ValueError):
    """A model output defect that may be returned for one bounded correction."""


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value
