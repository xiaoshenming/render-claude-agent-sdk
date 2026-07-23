"""Tool and exact-path guards enforced outside Agent prompts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from manim_quality.contracts._json_values import freeze_json_object, thaw_json_object
from manim_quality.revisions.fingerprint import sha256_text

from .profile import AgentProfile
from .read_tools import ReadonlyToolGrant
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


class ToolGuard:
    def __init__(
        self,
        *,
        workspace: Path,
        profile: AgentProfile,
        readable_paths: Sequence[Path],
        editable_paths: Sequence[Path],
        read_tools: Sequence[ReadonlyToolGrant] = (),
        tool_policies: Mapping[str, ToolInputPolicy] | None = None,
    ) -> None:
        if not isinstance(profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        self._profile = profile
        self._workspace = Path(workspace).resolve(strict=True)
        if not self._workspace.is_dir():
            raise PathDenied("workspace must be a directory")
        self._readable = self._declared_paths(readable_paths)
        self._editable = self._declared_paths(editable_paths)
        if self._editable and "Edit" not in profile.allowed_tools:
            raise ToolDenied("profile cannot declare editable paths")
        self._file_versions: dict[Path, int] = {}
        self._seen_reads: set[tuple[object, ...]] = set()
        self._seen_patches: set[tuple[str, str, str]] = set()
        self._read_tools = self._declared_read_tools(read_tools)
        self._read_tool_calls: dict[str, int] = {}
        self._pending_read_tools: dict[tuple[str, str], int] = {}
        self._tool_policies = self._declared_tool_policies(tool_policies or {})
        self._builtin_tool_calls: dict[str, int] = {}

    @property
    def readable_paths(self) -> tuple[str, ...]:
        paths = self._readable | self._editable
        return tuple(str(path) for path in sorted(paths))

    @property
    def editable_paths(self) -> tuple[str, ...]:
        return tuple(str(path) for path in sorted(self._editable))

    def authorize(self, tool: str, input_data: object) -> Mapping[str, object]:
        if tool in self._read_tools:
            return self._authorize_read_tool(tool, input_data)
        if tool not in self._profile.allowed_tools:
            raise ToolDenied(f"tool is not allowed for {self._profile.role}: {tool}")
        frozen = freeze_json_object(input_data, "tool_input")
        frozen = self._apply_tool_policy(tool, frozen)
        path = self._requested_path(frozen)
        if tool == "Read":
            self._authorize_read(path, frozen)
        elif tool == "Edit":
            self._authorize_edit(path, frozen)
        else:
            raise ToolDenied(f"unsupported allowed tool: {tool}")
        self._builtin_tool_calls[tool] = self._builtin_tool_calls.get(tool, 0) + 1
        normalized = dict(frozen)
        normalized["file_path"] = str(path)
        return freeze_json_object(normalized, "normalized_tool_input")

    def claim_read_tool(self, tool: str, input_data: object) -> ReadonlyToolGrant:
        grant = self._read_tools.get(tool)
        if grant is None:
            raise ToolDenied(f"read tool is not allowed: {tool}")
        normalized = grant.normalize_input(input_data)
        signature = (tool, _input_hash(normalized))
        pending = self._pending_read_tools.get(signature, 0)
        if pending <= 0:
            raise ToolDenied(f"read tool has no pending authorization: {tool}")
        if pending == 1:
            del self._pending_read_tools[signature]
        else:
            self._pending_read_tools[signature] = pending - 1
        return grant

    def _authorize_read_tool(
        self, tool: str, input_data: object
    ) -> Mapping[str, object]:
        grant = self._read_tools[tool]
        calls = self._read_tool_calls.get(tool, 0)
        if calls >= grant.max_calls:
            raise ToolDenied(f"read tool call limit exceeded: {tool}")
        normalized = grant.normalize_input(input_data)
        signature = (tool, _input_hash(normalized))
        self._read_tool_calls[tool] = calls + 1
        self._pending_read_tools[signature] = (
            self._pending_read_tools.get(signature, 0) + 1
        )
        return normalized

    def _authorize_read(self, path: Path, data: Mapping[str, object]) -> None:
        if path not in self._readable and path not in self._editable:
            raise PathDenied(f"read path is outside exact allowlist: {path}")
        signature = (
            str(path),
            self._file_versions.get(path, 0),
            data.get("offset"),
            data.get("limit"),
        )
        policy = self._tool_policies.get("Read")
        if signature in self._seen_reads and (
            policy is None or policy.max_calls <= 1
        ):
            raise DuplicateRead(f"duplicate Read call: {path}")
        self._seen_reads.add(signature)

    def _authorize_edit(self, path: Path, data: Mapping[str, object]) -> None:
        if path not in self._editable:
            raise PathDenied(f"edit path is outside exact allowlist: {path}")
        old_string = data.get("old_string")
        new_string = data.get("new_string")
        if not isinstance(old_string, str) or not isinstance(new_string, str):
            raise ToolDenied("Edit requires old_string and new_string")
        if old_string == new_string:
            raise ToolDenied("Edit must change content")
        signature = (str(path), old_string, new_string)
        if signature in self._seen_patches:
            raise DuplicatePatch(f"duplicate Edit patch: {path}")
        self._seen_patches.add(signature)
        self._file_versions[path] = self._file_versions.get(path, 0) + 1

    def _requested_path(self, data: Mapping[str, object]) -> Path:
        value = data.get("file_path")
        if not isinstance(value, str) or not value:
            raise PathDenied("tool requires a non-empty file_path")
        raw = Path(value)
        if ".." in raw.parts:
            raise PathDenied("parent traversal is forbidden")
        candidate = raw if raw.is_absolute() else self._workspace / raw
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            resolved = self._recover_duplicated_workspace(raw)
            if resolved is None:
                raise PathDenied(f"path cannot be resolved: {value}") from error
        if not resolved.is_relative_to(self._workspace):
            raise PathDenied(f"path escapes task workspace: {value}")
        if not resolved.is_file():
            raise PathDenied(f"path is not a file: {value}")
        return resolved

    def _recover_duplicated_workspace(self, raw: Path) -> Path | None:
        if not raw.is_absolute():
            return None
        workspace_parts = self._workspace.parts
        suffix = raw.parts[len(workspace_parts) :]
        if raw.parts[: len(workspace_parts)] != workspace_parts:
            return None
        if suffix[: len(workspace_parts) - 1] != workspace_parts[1:]:
            return None
        try:
            recovered = Path(raw.anchor, *suffix).resolve(strict=True)
        except OSError:
            return None
        return recovered if recovered.is_relative_to(self._workspace) else None

    def _declared_paths(self, values: Sequence[Path]) -> frozenset[Path]:
        paths: set[Path] = set()
        for value in values:
            raw = Path(value)
            if ".." in raw.parts:
                raise PathDenied("parent traversal is forbidden in allowlist")
            candidate = raw if raw.is_absolute() else self._workspace / raw
            try:
                resolved = candidate.resolve(strict=True)
            except OSError as error:
                raise PathDenied(
                    f"declared path cannot be resolved: {value}"
                ) from error
            if not resolved.is_relative_to(self._workspace):
                raise PathDenied(f"declared path escapes workspace: {value}")
            if not resolved.is_file():
                raise PathDenied(f"declared path is not a file: {value}")
            paths.add(resolved)
        return frozenset(paths)

    def _declared_read_tools(
        self, values: Sequence[ReadonlyToolGrant]
    ) -> Mapping[str, ReadonlyToolGrant]:
        tools: dict[str, ReadonlyToolGrant] = {}
        for value in values:
            if not isinstance(value, ReadonlyToolGrant):
                raise TypeError("read_tools must contain ReadonlyToolGrant values")
            if value.sdk_name in tools:
                raise ToolDenied(f"duplicate read tool grant: {value.sdk_name}")
            tools[value.sdk_name] = value
        return tools

    def _declared_tool_policies(
        self, values: Mapping[str, ToolInputPolicy]
    ) -> Mapping[str, ToolInputPolicy]:
        policies: dict[str, ToolInputPolicy] = {}
        for name, policy in values.items():
            if name not in self._profile.allowed_tools:
                raise ToolDenied(f"tool policy targets disallowed tool: {name}")
            if not isinstance(policy, ToolInputPolicy):
                raise TypeError("tool policies must contain ToolInputPolicy values")
            policies[name] = policy
        return policies

    def _apply_tool_policy(
        self, tool: str, input_data: Mapping[str, object]
    ) -> Mapping[str, object]:
        policy = self._tool_policies.get(tool)
        if policy is None:
            return input_data
        if self._builtin_tool_calls.get(tool, 0) >= policy.max_calls:
            raise ToolDenied(f"built-in tool call limit exceeded: {tool}")
        try:
            return policy.normalize(input_data)
        except (TypeError, ValueError) as error:
            raise ToolDenied(str(error)) from error


def _input_hash(value: Mapping[str, object]) -> str:
    canonical = json.dumps(
        thaw_json_object(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(canonical)
