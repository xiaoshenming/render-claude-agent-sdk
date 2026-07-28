from dataclasses import FrozenInstanceError

import anyio
import pytest

from manim_quality.agents.managed_tools import (
    ManagedToolContent,
    ManagedToolGrant,
    ManagedToolInputError,
    ManagedToolResultTooLarge,
    ManagedToolTimeout,
    ToolEffect,
)


async def echo(arguments):
    return f"value={arguments['value']}"


def grant(**changes) -> ManagedToolGrant:
    values = {
        "server_name": "quality",
        "name": "record_findings",
        "description": "Freeze findings before a patch.",
        "input_schema": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "handler": echo,
        "effect": ToolEffect.STATE_MUTATION,
        "max_calls": 1,
        "timeout_ms": 100,
        "max_result_chars": 100,
    }
    values.update(changes)
    return ManagedToolGrant(**values)


def test_managed_tool_grant_is_immutable_and_declares_effect() -> None:
    tool = grant()

    assert tool.sdk_name == "mcp__quality__record_findings"
    assert tool.effect is ToolEffect.STATE_MUTATION
    assert tool.context_bytes > 0
    with pytest.raises(FrozenInstanceError):
        tool.max_calls = 2  # type: ignore[misc]


def test_managed_tool_marks_model_argument_shape_as_correctable() -> None:
    with pytest.raises(ManagedToolInputError, match="unsupported fields"):
        grant().normalize_input({"value": "ok", "value2": "extra"})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("server_name", "bad name"),
        ("name", "Write"),
        ("effect", "mutation"),
        ("max_calls", 0),
        ("timeout_ms", 0),
        ("max_result_chars", 0),
    ],
)
def test_managed_tool_rejects_unsafe_configuration(field, value) -> None:
    with pytest.raises((TypeError, ValueError)):
        grant(**{field: value})


def test_managed_tool_executes_and_hashes_bounded_result() -> None:
    result = anyio.run(grant().execute, {"value": "ok"})

    assert result.text == "value=ok"
    assert result.status == "ok"
    assert result.result_hash.startswith("sha256:")
    assert result.content == ({"type": "text", "text": "value=ok"},)


def test_managed_tool_supports_auditable_image_content() -> None:
    async def image_result(_arguments):
        return ManagedToolContent(
            audit_text='{"frames":1}',
            blocks=(
                {"type": "text", "text": '{"frames":1}'},
                {"type": "image", "data": "YWJj", "mimeType": "image/png"},
            ),
        )

    result = anyio.run(grant(handler=image_result).execute, {"value": "ok"})

    assert result.text == '{"frames":1}'
    assert result.content[1]["type"] == "image"


def test_managed_tool_rejects_oversized_result() -> None:
    async def too_large(_arguments):
        return "x" * 101

    with pytest.raises(ManagedToolResultTooLarge):
        anyio.run(grant(handler=too_large).execute, {"value": "ok"})


def test_mutating_tool_requires_cancellable_async_handler() -> None:
    with pytest.raises(TypeError, match="async"):
        grant(handler=lambda _arguments: "unsafe")


def test_managed_tool_timeout_cancels_late_mutation() -> None:
    mutations: list[str] = []

    async def slow(_arguments):
        await anyio.sleep(0.05)
        mutations.append("late")
        return "late"

    with pytest.raises(ManagedToolTimeout):
        anyio.run(grant(handler=slow, timeout_ms=1).execute, {"value": "ok"})
    anyio.run(anyio.sleep, 0.06)

    assert mutations == []


def test_managed_tool_rejects_oversized_input() -> None:
    with pytest.raises(ValueError, match="input exceeds"):
        anyio.run(
            grant(max_input_bytes=20).execute,
            {"value": "x" * 100},
        )
