"""The single bounded SDK capability exposed by Geometry Inspector v1."""

from __future__ import annotations

from collections.abc import Mapping

from manim_quality.agents.read_tools import ReadonlyToolGrant

from .schemas import GeometrySnapshot
from .service import (
    SUPPORTED_RELATIONS,
    GeometryInspector,
    validate_inspection_arguments,
)

TOOL_SERVER = "geometry"
TOOL_NAME = "inspect_geometry_relation"


def geometry_inspector_tool(snapshot: GeometrySnapshot) -> ReadonlyToolGrant:
    inspector = GeometryInspector(snapshot)

    def inspect(arguments: Mapping[str, object]) -> str:
        return inspector.inspect_json(arguments)

    return ReadonlyToolGrant(
        server_name=TOOL_SERVER,
        name=TOOL_NAME,
        description=(
            "Evaluate one declared geometric relation over the bound render snapshot. "
            "Operands: line_endpoints=[line,start_point,end_point]; "
            "collinear=[point,point,point]; midpoint=[midpoint,start,end]; all "
            "other relations use two operands. point_on_line tests the infinite "
            "supporting line, not finite segment containment. Returns measured "
            "facts only, never a repair or delivery decision."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "relation": {
                    "type": "string",
                    "enum": sorted(SUPPORTED_RELATIONS),
                },
                "operands": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 2,
                    "maxItems": 3,
                },
            },
            "required": ["relation", "operands"],
            "additionalProperties": False,
        },
        input_validator=_validate_input,
        handler=inspect,
        max_calls=2,
        timeout_ms=200,
        max_result_chars=2_000,
    )


def _validate_input(arguments: Mapping[str, object]) -> None:
    validate_inspection_arguments(arguments)
