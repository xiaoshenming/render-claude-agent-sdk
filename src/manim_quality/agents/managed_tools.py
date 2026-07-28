"""Bounded in-process tools managed by the Agent Runtime."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from inspect import iscoroutinefunction

import anyio

from manim_quality.contracts._json_values import (
    freeze_json_object,
    thaw_json_object,
)
from manim_quality.revisions.fingerprint import sha256_text

ManagedToolHandler = Callable[
    [Mapping[str, object]],
    object | Awaitable[object],
]
ManagedToolValidator = Callable[[Mapping[str, object]], None]

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


class ToolEffect(StrEnum):
    READ_ONLY = "read_only"
    SESSION_MUTATION = "session_mutation"
    REVISION_MUTATION = "revision_mutation"
    VALIDATION = "validation"

    STATE_MUTATION = "session_mutation"


class ManagedToolError(RuntimeError):
    pass


class ManagedToolTimeout(ManagedToolError):
    pass


class ManagedToolResultTooLarge(ManagedToolError):
    pass


class ManagedToolInputError(ValueError):
    """A model-authored tool argument error that can be corrected next round."""


@dataclass(frozen=True, slots=True)
class ManagedToolResult:
    text: str
    status: str
    result_hash: str
    content: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class ManagedToolContent:
    """Auditable MCP content; image bytes are never copied into the call log."""

    audit_text: str
    blocks: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.audit_text, str):
            raise TypeError("audit_text must be a string")
        if not self.blocks:
            raise ValueError("blocks must not be empty")


@dataclass(frozen=True, slots=True)
class ManagedToolGrant:
    """One immutable structured capability granted to one Agent run."""

    server_name: str
    name: str
    description: str
    input_schema: Mapping[str, object]
    handler: ManagedToolHandler
    effect: ToolEffect
    max_calls: int
    timeout_ms: int
    max_result_chars: int
    input_validator: ManagedToolValidator | None = None
    max_input_bytes: int = 16_000

    def __post_init__(self) -> None:
        _require_safe_name(self.server_name, "server_name")
        _require_safe_name(self.name, "name")
        if self.name in _BUILTIN_NAMES:
            raise ValueError("managed tool name must not shadow a built-in tool")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("description must be a non-empty string")
        object.__setattr__(
            self,
            "input_schema",
            freeze_json_object(self.input_schema, "input_schema"),
        )
        if not callable(self.handler):
            raise TypeError("handler must be callable")
        if not isinstance(self.effect, ToolEffect):
            raise TypeError("effect must be a ToolEffect")
        if (
            self.effect is not ToolEffect.READ_ONLY
            and not iscoroutinefunction(self.handler)
        ):
            raise TypeError("mutating managed tool handler must be async")
        if self.input_validator is not None and not callable(self.input_validator):
            raise TypeError("input_validator must be callable or None")
        _require_positive_counts(self)

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
        try:
            normalized = freeze_json_object(value, "managed_tool_input")
            _validate_top_level_shape(normalized, self.input_schema)
            if _json_bytes(normalized) > self.max_input_bytes:
                raise ValueError(
                    f"managed tool input exceeds {self.max_input_bytes} bytes"
                )
            if self.input_validator is not None:
                self.input_validator(normalized)
        except (TypeError, ValueError) as error:
            raise ManagedToolInputError(str(error)) from error
        return normalized

    async def execute(self, value: object) -> ManagedToolResult:
        normalized = self.normalize_input(value)
        try:
            with anyio.fail_after(self.timeout_ms / 1_000):
                arguments = thaw_json_object(normalized)
                if iscoroutinefunction(self.handler):
                    text = await self.handler(arguments)
                else:
                    text = await anyio.to_thread.run_sync(
                        self.handler,
                        arguments,
                        abandon_on_cancel=True,
                    )
        except TimeoutError as error:
            raise ManagedToolTimeout(
                f"managed tool timed out: {self.sdk_name}"
            ) from error
        content = _normalize_content(text)
        if len(content.audit_text) > self.max_result_chars:
            raise ManagedToolResultTooLarge(
                f"managed tool result exceeds {self.max_result_chars} characters"
            )
        return ManagedToolResult(
            text=content.audit_text,
            status="ok",
            result_hash=sha256_text(content.audit_text),
            content=content.blocks,
        )


def _require_safe_name(value: object, field: str) -> str:
    if not isinstance(value, str) or _SAFE_NAME.fullmatch(value) is None:
        raise ValueError(f"{field} must be a safe lowercase identifier")
    return value


def _require_positive_counts(grant: ManagedToolGrant) -> None:
    for name in ("max_calls", "timeout_ms", "max_result_chars", "max_input_bytes"):
        value = getattr(grant, name)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")


def _validate_top_level_shape(
    value: Mapping[str, object], schema: Mapping[str, object]
) -> None:
    if schema.get("type") != "object":
        raise ValueError("managed tool input schema must describe an object")
    raw_required = schema.get("required", ())
    raw_properties = schema.get("properties")
    if not isinstance(raw_required, tuple) or not isinstance(raw_properties, Mapping):
        raise ValueError("managed tool input schema requires properties and required")
    missing = set(raw_required) - value.keys()
    if missing:
        raise ValueError(f"managed tool input is missing fields: {sorted(missing)}")
    if schema.get("additionalProperties") is not False:
        raise ValueError("managed tool input schema must forbid additional properties")
    extras = value.keys() - raw_properties.keys()
    if extras:
        raise ValueError(
            f"managed tool input has unsupported fields: {sorted(extras)}"
        )


def _json_bytes(value: Mapping[str, object]) -> int:
    text = json.dumps(
        thaw_json_object(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return len(text.encode("utf-8"))


def _normalize_content(value: object) -> ManagedToolContent:
    if isinstance(value, str):
        return ManagedToolContent(
            audit_text=value,
            blocks=({"type": "text", "text": value},),
        )
    if not isinstance(value, ManagedToolContent):
        raise TypeError("managed tool handler must return text or ManagedToolContent")
    for block in value.blocks:
        if not isinstance(block, Mapping) or block.get("type") not in {"text", "image"}:
            raise ValueError("managed tool content contains an unsupported block")
    return value
