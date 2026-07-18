import json

import anyio
import pytest

from manim_quality.geometry.schemas import parse_geometry_snapshot
from manim_quality.geometry.sdk_tool import geometry_inspector_tool

CODE_HASH = "sha256:" + "d" * 64


def _source(line: int) -> dict[str, object]:
    return {
        "scene_id": "Solution",
        "line_start": line,
        "line_end": line,
        "excerpt": f"object at line {line}",
    }


def _object(object_id, kind, state, line):
    return {
        "object_id": object_id,
        "kind": kind,
        "status": "known",
        "reason_code": None,
        "state": state,
        "source": _source(line),
    }


def _snapshot():
    objects = [
        _object("A", "point", {"position": [0, 0]}, 10),
        _object("B", "point", {"position": [2, 0]}, 11),
        _object("M", "point", {"position": [1, 0]}, 12),
        _object("P", "point", {"position": [1, 1]}, 13),
        _object("AB", "line", {"start": [0, 0], "end": [2, 0]}, 14),
        _object("vertical", "line", {"start": [1, -1], "end": [1, 1]}, 15),
        _object("parallel", "line", {"start": [0, 2], "end": [2, 2]}, 16),
        _object("circle", "circle", {"center": [0, 0], "radius": 1}, 17),
    ]
    return parse_geometry_snapshot(
        {
            "schema_version": "manim-quality.geometry-snapshot.v1",
            "code_hash": CODE_HASH,
            "scene_id": "Solution",
            "checkpoint_id": "final-visible",
            "provenance": "runtime_final",
            "objects": objects,
        }
    )


@pytest.mark.parametrize(
    ("relation", "operands", "truth"),
    [
        ("line_endpoints", ["AB", "A", "B"], True),
        ("point_on_line", ["M", "AB"], True),
        ("point_on_circle", ["P", "circle"], False),
        ("parallel", ["AB", "parallel"], True),
        ("perpendicular", ["AB", "vertical"], True),
        ("collinear", ["A", "M", "B"], True),
        ("equal_length", ["AB", "vertical"], True),
        ("midpoint", ["M", "A", "B"], True),
    ],
)
def test_single_sdk_tool_exposes_each_supported_relation(
    relation: str, operands: list[str], truth: bool
) -> None:
    tool = geometry_inspector_tool(_snapshot())

    result = anyio.run(tool.execute, {"relation": relation, "operands": operands})
    payload = json.loads(result.text)

    assert tool.sdk_name == "mcp__geometry__inspect_geometry_relation"
    assert payload["status"] == "known"
    assert payload["truth"] is truth
    assert payload["relation"] == relation
    assert payload["snapshot_provenance"] == "runtime_final"
    assert payload["code_hash"] == CODE_HASH
    assert len(result.text) <= 2_000


@pytest.mark.parametrize(
    "arguments",
    [
        {"relation": "parallel", "operands": ["AB", "parallel"], "path": "x"},
        {"relation": "parallel", "operands": ["AB", "parallel"], "code": "x"},
        {"relation": "distance", "operands": ["A", "B"]},
        {"relation": "parallel", "operands": ["A", "B", "M", "P", "AB"]},
        {"relation": "parallel", "operands": ["A", 2]},
        {"relation": "line_endpoints", "operands": ["AB"]},
    ],
)
def test_sdk_tool_rejects_paths_code_unknown_relations_and_invalid_operands(
    arguments,
) -> None:
    tool = geometry_inspector_tool(_snapshot())

    with pytest.raises((TypeError, ValueError)):
        anyio.run(tool.execute, arguments)


def test_sdk_tool_returns_unknown_for_missing_snapshot_entity() -> None:
    tool = geometry_inspector_tool(_snapshot())

    result = anyio.run(
        tool.execute,
        {"relation": "parallel", "operands": ["AB", "missing"]},
    )
    payload = json.loads(result.text)

    assert payload["status"] == "unknown"
    assert payload["truth"] is None
    assert payload["reason_code"] == "missing_entity"


def test_sdk_tool_configuration_is_hard_bounded() -> None:
    tool = geometry_inspector_tool(_snapshot())

    assert tool.max_calls == 2
    assert tool.timeout_ms == 200
    assert tool.max_result_chars == 2_000
    assert tool.input_schema["additionalProperties"] is False
