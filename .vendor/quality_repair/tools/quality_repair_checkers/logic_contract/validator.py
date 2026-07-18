"""Dispatcher for logic-contract validators."""

from __future__ import annotations

from typing import Any

from .geometry_validators import (
    check_angle_measure,
    check_claim_geometry,
    check_distance_between_points,
    check_equal_length,
    check_line_endpoint_match,
    check_perpendicular_lines,
    check_point_coordinate,
    check_point_on_line,
    check_reflection_point,
)
from .loader import GeometryEvidence
from .text_validators import check_no_unescaped_latex_command, check_source_contains, check_source_not_contains

CLAIM_GEOMETRY_KINDS = {
    "foot_point",
    "line_intersection",
    "points_collinear",
    "line_perpendicular",
    "angle_equals_degrees",
    "angle_equals_angle",
    "length_equals_length",
}


def validate_contract(contract: dict[str, Any], geometry: GeometryEvidence, source: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    points = geometry.points
    for item in contract_items(contract):
        kind = str(item.get("kind") or contract.get("kind") or "")
        if kind == "equal_length":
            issues.extend(check_equal_length(item, contract, points))
        elif kind == "point_coordinate":
            issues.extend(check_point_coordinate(item, contract, points))
        elif kind == "distance_between_points":
            issues.extend(check_distance_between_points(item, contract, points))
        elif kind == "perpendicular_lines":
            issues.extend(check_perpendicular_lines(item, contract, points))
        elif kind in {"source_contains", "must_contain"}:
            issues.extend(check_source_contains(item, source))
        elif kind in {"source_not_contains", "must_not_contain", "forbid_text"}:
            issues.extend(check_source_not_contains(item, source))
        elif kind == "no_unescaped_latex_command":
            issues.extend(check_no_unescaped_latex_command(item, source))
        elif kind == "point_on_line":
            issues.extend(check_point_on_line(item, points))
        elif kind == "reflection_point":
            issues.extend(check_reflection_point(item, points))
        elif kind == "angle_measure":
            issues.extend(check_angle_measure(item, points, source))
        elif kind == "line_endpoint_match":
            issues.extend(check_line_endpoint_match(item, points, geometry.line_segments))
        elif kind in CLAIM_GEOMETRY_KINDS:
            issues.extend(check_claim_geometry(kind, item, points, source))
        elif contract.get("expected_coords") and contract.get("target"):
            issues.extend(check_point_coordinate(item, contract, points))
        else:
            issues.append({"kind": "unsupported_contract", "contract_kind": kind})
    return issues


def contract_items(contract: dict[str, Any]) -> list[dict[str, Any]]:
    value = contract.get("contracts")
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if str(contract.get("kind") or "") in {"", "none"}:
        return []
    return [contract]
