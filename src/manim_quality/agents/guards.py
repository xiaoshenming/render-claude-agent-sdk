"""Tool and exact-path guards enforced outside Agent prompts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from manim_quality.contracts._json_values import freeze_json_object

from ._agent_tool_input import normalize_reviewer_agent_input
from ._guard_primitives import (
    DuplicatePatch,
    PathDenied,
    ToolDenied,
    declare_managed_tools,
    declare_paths,
    declare_read_tools,
    declare_subagents,
    declare_tool_policies,
    input_hash,
    resolve_requested_path,
)
from ._guard_primitives import DuplicateRead as DuplicateRead
from ._guard_primitives import GuardError as GuardError
from .managed_tools import ManagedToolGrant
from .profile import AgentProfile
from .read_tools import ReadonlyToolGrant
from .subagents import NativeSubagentSpec
from .tool_policy import ToolInputPolicy


class ToolGuard:
    def __init__(
        self,
        *,
        workspace: Path,
        profile: AgentProfile,
        readable_paths: Sequence[Path],
        editable_paths: Sequence[Path],
        read_tools: Sequence[ReadonlyToolGrant] = (),
        managed_tools: Sequence[ManagedToolGrant] = (),
        tool_policies: Mapping[str, ToolInputPolicy] | None = None,
        subagents: Sequence[NativeSubagentSpec] = (),
    ) -> None:
        if not isinstance(profile, AgentProfile):
            raise TypeError("profile must be AgentProfile")
        self._profile = profile
        self._workspace = Path(workspace).resolve(strict=True)
        if not self._workspace.is_dir():
            raise PathDenied("workspace must be a directory")
        self._readable = declare_paths(self._workspace, readable_paths)
        self._editable = declare_paths(self._workspace, editable_paths)
        if self._editable and "Edit" not in profile.allowed_tools:
            raise ToolDenied("profile cannot declare editable paths")
        self._file_versions: dict[Path, int] = {}
        self._seen_patches: set[tuple[str, str, str]] = set()
        self._read_tools = declare_read_tools(read_tools)
        self._managed_tools = declare_managed_tools(managed_tools)
        duplicates = self._read_tools.keys() & self._managed_tools.keys()
        if duplicates:
            raise ToolDenied(f"duplicate managed tool grant: {sorted(duplicates)}")
        self._read_tool_calls: dict[tuple[str, str], int] = {}
        self._pending_read_tools: dict[tuple[str, str], int] = {}
        self._tool_policies = declare_tool_policies(
            tool_policies or {}, self._profile
        )
        self._builtin_tool_calls: dict[str, int] = {}
        self._subagents = declare_subagents(
            subagents,
            profile=self._profile,
            read_tools=self._read_tools,
            managed_tools=self._managed_tools,
        )
        self._invoked_subagents: set[str] = set()

    @property
    def readable_paths(self) -> tuple[str, ...]:
        paths = self._readable | self._editable
        return tuple(str(path) for path in sorted(paths))

    @property
    def editable_paths(self) -> tuple[str, ...]:
        return tuple(str(path) for path in sorted(self._editable))

    def authorize(
        self,
        tool: str,
        input_data: object,
        *,
        agent_id: str | None = None,
        agent_type: str | None = None,
    ) -> Mapping[str, object]:
        if agent_id is not None:
            return self._authorize_subagent_tool(
                tool,
                input_data,
                agent_id=agent_id,
                agent_type=agent_type,
            )
        if tool == "Task" and "Agent" in self._profile.allowed_tools:
            tool = "Agent"
        if tool in self._managed_tools:
            return self._authorize_managed_tool(tool, input_data, caller="parent")
        if tool in self._read_tools:
            return self._authorize_read_tool(tool, input_data, caller="parent")
        if tool not in self._profile.allowed_tools:
            raise ToolDenied(f"tool is not allowed for {self._profile.role}: {tool}")
        if tool == "Agent":
            return self._authorize_agent(input_data)
        frozen = freeze_json_object(input_data, "tool_input")
        frozen = self._apply_tool_policy(tool, frozen)
        path = resolve_requested_path(self._workspace, frozen)
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
        signature = (tool, input_hash(normalized))
        pending = self._pending_read_tools.get(signature, 0)
        if pending <= 0:
            raise ToolDenied(f"read tool has no pending authorization: {tool}")
        if pending == 1:
            del self._pending_read_tools[signature]
        else:
            self._pending_read_tools[signature] = pending - 1
        return grant

    def claim_managed_tool(
        self, tool: str, input_data: object
    ) -> ManagedToolGrant:
        grant = self._managed_tools.get(tool)
        if grant is None:
            raise ToolDenied(f"managed tool is not allowed: {tool}")
        normalized = grant.normalize_input(input_data)
        self._claim_pending_tool(tool, normalized)
        return grant
    def refund_parent_managed_tool(self, tool: str) -> None:
        call_key = ("parent", tool)
        if self._read_tool_calls.get(call_key, 0) <= 0:
            raise ToolDenied(f"managed tool has no call to refund: {tool}")
        self._read_tool_calls[call_key] -= 1

    def _authorize_read_tool(
        self, tool: str, input_data: object, *, caller: str
    ) -> Mapping[str, object]:
        grant = self._read_tools[tool]
        return self._authorize_external_tool(tool, input_data, grant, caller=caller)

    def _authorize_managed_tool(
        self, tool: str, input_data: object, *, caller: str
    ) -> Mapping[str, object]:
        grant = self._managed_tools[tool]
        return self._authorize_external_tool(tool, input_data, grant, caller=caller)

    def _authorize_external_tool(
        self,
        tool: str,
        input_data: object,
        grant: ReadonlyToolGrant | ManagedToolGrant,
        *,
        caller: str,
    ) -> Mapping[str, object]:
        call_key = (caller, tool)
        calls = self._read_tool_calls.get(call_key, 0)
        if calls >= grant.max_calls:
            raise ToolDenied(f"managed tool call limit exceeded: {tool}")
        normalized = grant.normalize_input(input_data)
        signature = (tool, input_hash(normalized))
        self._read_tool_calls[call_key] = calls + 1
        self._pending_read_tools[signature] = (
            self._pending_read_tools.get(signature, 0) + 1
        )
        return normalized

    def _authorize_agent(self, input_data: object) -> Mapping[str, object]:
        value = normalize_reviewer_agent_input(
            input_data, self._subagents, self._invoked_subagents,
        )
        self._builtin_tool_calls["Agent"] = (
            self._builtin_tool_calls.get("Agent", 0) + 1
        )
        return value

    def _authorize_subagent_tool(
        self,
        tool: str,
        input_data: object,
        *,
        agent_id: str,
        agent_type: str | None,
    ) -> Mapping[str, object]:
        if not isinstance(agent_type, str) or agent_type not in self._subagents:
            raise ToolDenied("tool call came from an unknown subagent")
        spec = self._subagents[agent_type]
        if tool not in spec.allowed_tools:
            raise ToolDenied(f"tool is not allowed for Reviewer {agent_type}: {tool}")
        if tool in self._managed_tools:
            return self._authorize_managed_tool(
                tool,
                input_data,
                caller=agent_id,
            )
        if tool in self._read_tools:
            return self._authorize_read_tool(
                tool,
                input_data,
                caller=agent_id,
            )
        raise ToolDenied("Reviewer tools must be registered MCP capabilities")

    def _claim_pending_tool(
        self, tool: str, normalized: Mapping[str, object]
    ) -> None:
        signature = (tool, input_hash(normalized))
        pending = self._pending_read_tools.get(signature, 0)
        if pending <= 0:
            raise ToolDenied(f"managed tool has no pending authorization: {tool}")
        if pending == 1:
            del self._pending_read_tools[signature]
        else:
            self._pending_read_tools[signature] = pending - 1

    def _authorize_read(self, path: Path, data: Mapping[str, object]) -> None:
        del data
        if path not in self._readable and path not in self._editable:
            raise PathDenied(f"read path is outside exact allowlist: {path}")
        # Reads have no mutation side effects. Repeated reads still consume
        # the existing call/turn budgets and read current file contents.

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
