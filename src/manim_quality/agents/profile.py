"""Immutable role profiles for SDK-backed quality agents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

DEFAULT_SCHEMA_VERSION = "agent-output-v1"
DEFAULT_TOOL_VERSION = "claude-builtin-v1"


class AgentRole(StrEnum):
    REVIEWER = "reviewer"
    CODER = "coder"
    VERIFIER = "verifier"
    OPERATOR = "operator"
    ASSURANCE = "assurance"


@dataclass(frozen=True, slots=True)
class AgentProfile:
    role: AgentRole
    model: str
    prompt_version: str
    schema_version: str
    tool_version: str
    allowed_tools: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.role, AgentRole):
            raise TypeError("role must be an AgentRole")
        for name in ("model", "prompt_version", "schema_version", "tool_version"):
            _require_text(getattr(self, name), name)
        if not isinstance(self.allowed_tools, frozenset):
            raise ValueError("allowed_tools must be a non-empty frozenset")
        expected = {
            AgentRole.REVIEWER: frozenset({"Read"}),
            AgentRole.CODER: frozenset({"Read", "Edit"}),
            AgentRole.VERIFIER: frozenset({"Read"}),
            AgentRole.OPERATOR: frozenset({"Agent"}),
            AgentRole.ASSURANCE: frozenset({"Agent"}),
        }[self.role]
        if self.allowed_tools != expected:
            raise ValueError(f"allowed_tools do not match {self.role} profile")


def reviewer_profile(
    *,
    model: str,
    prompt_version: str,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    tool_version: str = DEFAULT_TOOL_VERSION,
) -> AgentProfile:
    return AgentProfile(
        role=AgentRole.REVIEWER,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        tool_version=tool_version,
        allowed_tools=frozenset({"Read"}),
    )


def coder_profile(
    *,
    model: str,
    prompt_version: str,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    tool_version: str = DEFAULT_TOOL_VERSION,
) -> AgentProfile:
    return AgentProfile(
        role=AgentRole.CODER,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        tool_version=tool_version,
        allowed_tools=frozenset({"Read", "Edit"}),
    )


def verifier_profile(
    *,
    model: str,
    prompt_version: str,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    tool_version: str = DEFAULT_TOOL_VERSION,
) -> AgentProfile:
    return AgentProfile(
        role=AgentRole.VERIFIER,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        tool_version=tool_version,
        allowed_tools=frozenset({"Read"}),
    )


def operator_profile(
    *,
    model: str,
    prompt_version: str,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    tool_version: str = DEFAULT_TOOL_VERSION,
) -> AgentProfile:
    return AgentProfile(
        role=AgentRole.OPERATOR,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        tool_version=tool_version,
        allowed_tools=frozenset({"Agent"}),
    )


def assurance_profile(
    *,
    model: str,
    prompt_version: str,
    schema_version: str = DEFAULT_SCHEMA_VERSION,
    tool_version: str = DEFAULT_TOOL_VERSION,
) -> AgentProfile:
    return AgentProfile(
        role=AgentRole.ASSURANCE,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        tool_version=tool_version,
        allowed_tools=frozenset({"Agent"}),
    )


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value
