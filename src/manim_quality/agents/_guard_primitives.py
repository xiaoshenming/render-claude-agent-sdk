"""Stateless declarations and path checks used by the Agent tool guard."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.revisions.fingerprint import sha256_text

from .managed_tools import ManagedToolGrant
from .profile import AgentProfile
from .read_tools import ReadonlyToolGrant
from .subagents import NativeSubagentSpec
from .tool_policy import ToolInputPolicy


class GuardError(RuntimeError):
    pass


class ToolDenied(GuardError):
    pass


class PathDenied(GuardError):
    pass


class DuplicateRead(GuardError):
    pass


class DuplicatePatch(GuardError):
    pass


def resolve_requested_path(
    workspace: Path, data: Mapping[str, object]
) -> Path:
    value = data.get("file_path")
    if not isinstance(value, str) or not value:
        raise PathDenied("tool requires a non-empty file_path")
    raw = Path(value)
    if ".." in raw.parts:
        raise PathDenied("parent traversal is forbidden")
    candidate = raw if raw.is_absolute() else workspace / raw
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        raise PathDenied(f"path cannot be resolved: {value}") from error
    if not resolved.is_relative_to(workspace):
        raise PathDenied(f"path escapes task workspace: {value}")
    if not resolved.is_file():
        raise PathDenied(f"path is not a file: {value}")
    return resolved


def declare_paths(workspace: Path, values: Sequence[Path]) -> frozenset[Path]:
    paths: set[Path] = set()
    for value in values:
        raw = Path(value)
        if ".." in raw.parts:
            raise PathDenied("parent traversal is forbidden in allowlist")
        candidate = raw if raw.is_absolute() else workspace / raw
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise PathDenied(f"declared path cannot be resolved: {value}") from error
        if not resolved.is_relative_to(workspace):
            raise PathDenied(f"declared path escapes workspace: {value}")
        if not resolved.is_file():
            raise PathDenied(f"declared path is not a file: {value}")
        paths.add(resolved)
    return frozenset(paths)


def declare_read_tools(
    values: Sequence[ReadonlyToolGrant],
) -> Mapping[str, ReadonlyToolGrant]:
    tools: dict[str, ReadonlyToolGrant] = {}
    for value in values:
        if not isinstance(value, ReadonlyToolGrant):
            raise TypeError("read_tools must contain ReadonlyToolGrant values")
        if value.sdk_name in tools:
            raise ToolDenied(f"duplicate read tool grant: {value.sdk_name}")
        tools[value.sdk_name] = value
    return tools


def declare_managed_tools(
    values: Sequence[ManagedToolGrant],
) -> Mapping[str, ManagedToolGrant]:
    tools: dict[str, ManagedToolGrant] = {}
    for value in values:
        if not isinstance(value, ManagedToolGrant):
            raise TypeError("managed_tools must contain ManagedToolGrant values")
        if value.sdk_name in tools:
            raise ToolDenied(f"duplicate managed tool grant: {value.sdk_name}")
        tools[value.sdk_name] = value
    return tools


def declare_tool_policies(
    values: Mapping[str, ToolInputPolicy], profile: AgentProfile
) -> Mapping[str, ToolInputPolicy]:
    policies: dict[str, ToolInputPolicy] = {}
    for name, policy in values.items():
        if name not in profile.allowed_tools:
            raise ToolDenied(f"tool policy targets disallowed tool: {name}")
        if not isinstance(policy, ToolInputPolicy):
            raise TypeError("tool policies must contain ToolInputPolicy values")
        policies[name] = policy
    return policies


def declare_subagents(
    values: Sequence[NativeSubagentSpec],
    *,
    profile: AgentProfile,
    read_tools: Mapping[str, ReadonlyToolGrant],
    managed_tools: Mapping[str, ManagedToolGrant],
) -> Mapping[str, NativeSubagentSpec]:
    specs: dict[str, NativeSubagentSpec] = {}
    for value in values:
        if not isinstance(value, NativeSubagentSpec):
            raise TypeError("subagents must contain NativeSubagentSpec values")
        if value.name in specs:
            raise ToolDenied(f"duplicate subagent definition: {value.name}")
        unknown = set(value.allowed_tools) - (
            read_tools.keys() | managed_tools.keys()
        )
        if unknown:
            raise ToolDenied(
                f"subagent references undeclared tools: {sorted(unknown)}"
            )
        specs[value.name] = value
    if specs and "Agent" not in profile.allowed_tools:
        raise ToolDenied("subagents require the Agent built-in")
    return specs


def input_hash(value: Mapping[str, object]) -> str:
    canonical = json.dumps(
        thaw_json_object(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(canonical)
