"""Immutable native subagent definitions at the runtime boundary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


@dataclass(frozen=True, slots=True)
class NativeSubagentSpec:
    name: str
    description: str
    prompt: str
    allowed_tools: tuple[str, ...]
    max_turns: int = 5
    effort: str = "low"
    prompt_version: str = "v1"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or _SAFE_NAME.fullmatch(self.name) is None:
            raise ValueError("subagent name must be a safe lowercase identifier")
        for field in ("description", "prompt", "prompt_version"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a non-empty string")
        tools = tuple(self.allowed_tools)
        if not tools or any(
            not isinstance(item, str) or not item.startswith("mcp__")
            for item in tools
        ):
            raise ValueError("subagent tools must be explicit MCP tool names")
        if len(set(tools)) != len(tools):
            raise ValueError("subagent tools must be unique")
        object.__setattr__(self, "allowed_tools", tools)
        if (
            isinstance(self.max_turns, bool)
            or not isinstance(self.max_turns, int)
            or not 1 <= self.max_turns <= 8
        ):
            raise ValueError("subagent max_turns must be between 1 and 8")
        if self.effort not in _EFFORTS:
            raise ValueError("unsupported subagent effort")

    @property
    def context_bytes(self) -> int:
        value = {
            "name": self.name,
            "description": self.description,
            "prompt": self.prompt,
            "allowed_tools": self.allowed_tools,
            "max_turns": self.max_turns,
            "effort": self.effort,
        }
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
