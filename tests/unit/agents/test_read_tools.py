import time
from dataclasses import FrozenInstanceError

import anyio
import pytest

from manim_quality.agents.read_tools import (
    ReadonlyToolGrant,
    ReadToolResultTooLarge,
    ReadToolTimeout,
)


def echo(arguments):
    return f"value={arguments['value']}"


def grant(**changes) -> ReadonlyToolGrant:
    values = {
        "server_name": "geometry",
        "name": "inspect_relation",
        "description": "Inspect one relation.",
        "input_schema": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "handler": echo,
        "max_calls": 2,
        "timeout_ms": 100,
        "max_result_chars": 100,
    }
    values.update(changes)
    return ReadonlyToolGrant(**values)


def test_readonly_tool_grant_is_immutable_and_has_stable_sdk_name() -> None:
    tool = grant()

    assert tool.sdk_name == "mcp__geometry__inspect_relation"
    assert tool.input_schema["required"] == ("value",)
    with pytest.raises(FrozenInstanceError):
        tool.max_calls = 3  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("server_name", "bad name"),
        ("name", "Read"),
        ("max_calls", 0),
        ("timeout_ms", 0),
        ("max_result_chars", 0),
    ],
)
def test_readonly_tool_grant_rejects_unsafe_configuration(field, value) -> None:
    with pytest.raises((TypeError, ValueError)):
        grant(**{field: value})


def test_readonly_tool_executes_bounded_text_result() -> None:
    result = anyio.run(grant().execute, {"value": "ok"})

    assert result.text == "value=ok"
    assert result.status == "ok"
    assert result.result_hash.startswith("sha256:")


def test_readonly_tool_rejects_oversized_result() -> None:
    def too_large(_arguments):
        return "x" * 101

    with pytest.raises(ReadToolResultTooLarge):
        anyio.run(grant(handler=too_large).execute, {"value": "ok"})


def test_readonly_tool_enforces_its_own_timeout() -> None:
    def slow(_arguments):
        time.sleep(0.1)
        return "late"

    with pytest.raises(ReadToolTimeout):
        anyio.run(grant(handler=slow, timeout_ms=1).execute, {"value": "ok"})
