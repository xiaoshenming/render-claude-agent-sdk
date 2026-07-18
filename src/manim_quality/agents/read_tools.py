"""Explicit grants for bounded, in-process, read-only SDK tools."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from inspect import iscoroutinefunction

import anyio

from manim_quality.contracts._json_values import (
    freeze_json_object,
    thaw_json_object,
)
from manim_quality.revisions.fingerprint import sha256_text

ReadToolHandler = Callable[[Mapping[str, object]], str]
ReadToolValidator = Callable[[Mapping[str, object]], None]

_SAFE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_BUILTIN_NAMES = frozenset(
    {
        "Agent",
        "Bash",
        "Edit",
        "Read",
        "StructuredOutput",
        "Task",
        "WebFetch",
        "WebSearch",
        "Write",
    }
)


class ReadToolError(RuntimeError):
    pass


class ReadToolTimeout(ReadToolError):
    pass


class ReadToolResultTooLarge(ReadToolError):
    pass


@dataclass(frozen=True, slots=True)
class ReadToolResult:
    text: str
    status: str
    result_hash: str


@dataclass(frozen=True, slots=True)
class ReadonlyToolGrant:
    """One immutable capability granted to one Agent run."""

    server_name: str
    name: str
    description: str
    input_schema: Mapping[str, object]
    handler: ReadToolHandler
    max_calls: int
    timeout_ms: int
    max_result_chars: int
    input_validator: ReadToolValidator | None = None

    def __post_init__(self) -> None:
        _require_safe_name(self.server_name, "server_name")
        _require_safe_name(self.name, "name")
        if self.name in _BUILTIN_NAMES:
            raise ValueError("read tool name must not shadow a built-in tool")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a non-empty string")
        object.__setattr__(
            self,
            "input_schema",
            freeze_json_object(self.input_schema, "input_schema"),
        )
        if not callable(self.handler) or iscoroutinefunction(self.handler):
            raise TypeError("handler must be a synchronous callable")
        if self.input_validator is not None and not callable(self.input_validator):
            raise TypeError("input_validator must be callable or None")
        for name in ("max_calls", "timeout_ms", "max_result_chars"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")

    @property
    def sdk_name(self) -> str:
        return f"mcp__{self.server_name}__{self.name}"

    @property
    def context_bytes(self) -> int:
        definition = {
            "name": self.sdk_name,
            "description": self.description,
            "input_schema": thaw_json_object(self.input_schema),
        }
        text = json.dumps(
            definition,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return len(text.encode("utf-8"))

    def normalize_input(self, value: object) -> Mapping[str, object]:
        normalized = freeze_json_object(value, "read_tool_input")
        _validate_top_level_shape(normalized, self.input_schema)
        if self.input_validator is not None:
            self.input_validator(normalized)
        return normalized

    async def execute(self, value: object) -> ReadToolResult:
        normalized = self.normalize_input(value)
        try:
            with anyio.fail_after(self.timeout_ms / 1_000):
                text = await anyio.to_thread.run_sync(
                    self.handler,
                    thaw_json_object(normalized),
                    abandon_on_cancel=True,
                )
        except TimeoutError as error:
            raise ReadToolTimeout(f"read tool timed out: {self.sdk_name}") from error
        if not isinstance(text, str):
            raise TypeError("read tool handler must return text")
        if len(text) > self.max_result_chars:
            raise ReadToolResultTooLarge(
                f"read tool result exceeds {self.max_result_chars} characters"
            )
        return ReadToolResult(
            text=text,
            status="ok",
            result_hash=sha256_text(text),
        )


def _require_safe_name(value: object, field: str) -> str:
    if not isinstance(value, str) or _SAFE_NAME.fullmatch(value) is None:
        raise ValueError(f"{field} must be a safe lowercase identifier")
    return value


def _validate_top_level_shape(
    value: Mapping[str, object], schema: Mapping[str, object]
) -> None:
    if schema.get("type") != "object":
        raise ValueError("read tool input schema must describe an object")
    raw_required = schema.get("required", ())
    raw_properties = schema.get("properties")
    if not isinstance(raw_required, tuple) or not isinstance(raw_properties, Mapping):
        raise ValueError("read tool input schema requires properties and required")
    required = set(raw_required)
    missing = required - value.keys()
    if missing:
        raise ValueError(f"read tool input is missing fields: {sorted(missing)}")
    if schema.get("additionalProperties") is not False:
        raise ValueError("read tool input schema must forbid additional properties")
    extras = value.keys() - raw_properties.keys()
    if extras:
        raise ValueError(f"read tool input has unsupported fields: {sorted(extras)}")
