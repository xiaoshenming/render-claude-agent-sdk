"""Geometry validators for logic contracts."""

from __future__ import annotations

from typing import Any

from .math_utils import (
    angle_degrees,
    claim_was_removed,
    close,
    coords,
    distance,
    foot_point,
    line_intersection,
    number,
    point_line_distance,
    point_pair,
    point_triple,
    reflect_point,
    segment_matches_points,
    vector,
)

PointMap = dict[str, tuple[float, float, float]]


def check_equal_length(item: dict[str, Any], contract: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    target = str(item.get("target") or item.get("move_point") or contract.get("target") or "")
    expected_coords = coords(item.get("expected_coords") or contract.get("expected_coords"))
    if target and expected_coords is not None:
        issues.extend(point_mismatch_issue(target, expected_coords, points))
        if issues:
            return issues
    segment_a = point_pair(item.get("segment_a"))
    segment_b = point_pair(item.get("segment_b"))
    if segment_a and segment_b and all(name in points for name in (*segment_a, *segment_b)):
        length_a = distance(points[segment_a[0]], points[segment_a[1]])
        length_b = distance(points[segment_b[0]], points[segment_b[1]])
        if not close(length_a, length_b):
            issues.append({"kind": "equal_length_wrong", "segment_a": list(segment_a), "segment_b": list(segment_b), "expected_length": length_a, "actual_length": length_b})
    return issues


def check_point_coordinate(item: dict[str, Any], contract: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    target = str(item.get("target") or item.get("move_point") or contract.get("target") or "")
    expected = coords(item.get("expected_coords") or contract.get("expected_coords"))
    if not target or expected is None:
        return [{"kind": "point_coordinate_missing_expected", "target": target}]
    return point_mismatch_issue(target, expected, points)


def check_distance_between_points(item: dict[str, Any], contract: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    pair = point_pair(item.get("points") or item.get("segment") or item.get("segment_a"))
    expected = number(contract.get("expected_length") or contract.get("expected_value") or item.get("expected_length"))
    if not pair or expected is None:
        return [{"kind": "distance_contract_missing_expected"}]
    if pair[0] not in points or pair[1] not in points:
        return [{"kind": "point_not_found", "points": list(pair)}]
    actual = distance(points[pair[0]], points[pair[1]])
    return [] if close(actual, expected) else [{"kind": "distance_between_points_wrong", "points": list(pair), "expected": expected, "actual": actual}]


def check_perpendicular_lines(item: dict[str, Any], _contract: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    line_a = point_pair(item.get("line_a") or item.get("segment_a"))
    line_b = point_pair(item.get("line_b") or item.get("segment_b"))
    if not line_a or not line_b:
        return [{"kind": "perpendicular_contract_missing_lines"}]
    if not all(name in points for name in (*line_a, *line_b)):
        return [{"kind": "point_not_found", "points": list((*line_a, *line_b))}]
    dot = sum(a * b for a, b in zip(vector(points[line_a[0]], points[line_a[1]]), vector(points[line_b[0]], points[line_b[1]]), strict=True))
    return [] if abs(dot) <= 1e-4 else [{"kind": "perpendicular_lines_wrong", "line_a": list(line_a), "line_b": list(line_b), "dot": dot}]


def check_point_on_line(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    target = str(item.get("target") or "")
    line = point_pair(item.get("line"))
    if not target or not line:
        return [{"kind": "point_on_line_missing_expected", "target": target}]
    if target not in points or line[0] not in points or line[1] not in points:
        return [{"kind": "point_not_found", "points": [target, *line]}]
    dist = point_line_distance(points[target], points[line[0]], points[line[1]])
    return [] if dist <= 1e-3 else [{"kind": "point_not_on_line", "target": target, "line": list(line), "distance": dist}]


def check_reflection_point(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    target = str(item.get("target") or "")
    source = str(item.get("source") or "")
    line = point_pair(item.get("line"))
    if not target or not source or not line:
        return [{"kind": "reflection_contract_missing_expected", "target": target}]
    if target not in points or source not in points or line[0] not in points or line[1] not in points:
        return [{"kind": "point_not_found", "points": [target, source, *line]}]
    expected = reflect_point(points[source], points[line[0]], points[line[1]])
    actual = points[target]
    return [] if distance(actual, expected) <= 1e-3 else [{"kind": "reflection_point_wrong", "target": target, "source": source, "line": list(line), "expected_coords": list(expected), "actual_coords": list(actual)}]


def check_angle_measure(item: dict[str, Any], points: PointMap, source: str) -> list[dict[str, Any]]:
    claim_text = str(item.get("claim_text") or "")
    if claim_text and claim_text not in source:
        return []
    angle_points = point_triple(item.get("points"))
    expected = number(item.get("expected_degrees"))
    if not angle_points or expected is None:
        return [{"kind": "angle_measure_missing_expected"}]
    if not all(name in points for name in angle_points):
        return [{"kind": "point_not_found", "points": list(angle_points)}]
    actual = angle_degrees(points[angle_points[0]], points[angle_points[1]], points[angle_points[2]])
    return [] if abs(actual - expected) <= 1.0 else [{"kind": "angle_measure_wrong", "points": list(angle_points), "expected_degrees": expected, "actual_degrees": actual}]


def check_line_endpoint_match(item: dict[str, Any], points: PointMap, line_segments: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]]) -> list[dict[str, Any]]:
    target = str(item.get("target") or "")
    endpoints = point_pair(item.get("endpoints"))
    if not target or not endpoints:
        return [{"kind": "line_endpoint_missing_expected", "target": target}]
    if target not in line_segments:
        return [{"kind": "line_segment_not_found", "target": target}]
    if endpoints[0] not in points or endpoints[1] not in points:
        return [{"kind": "point_not_found", "points": list(endpoints)}]
    actual = line_segments[target]
    expected = (points[endpoints[0]], points[endpoints[1]])
    if segment_matches_points(actual, expected):
        return []
    return [{"kind": "line_endpoint_mismatch", "target": target, "endpoints": list(endpoints), "expected_coords": [list(expected[0]), list(expected[1])], "actual_coords": [list(actual[0]), list(actual[1])]}]


def point_mismatch_issue(target: str, expected: tuple[float, float, float], points: PointMap) -> list[dict[str, Any]]:
    actual = points.get(target)
    if actual is None:
        return [{"kind": "point_not_found", "target": target}]
    if all(close(a, e) for a, e in zip(actual, expected, strict=True)):
        return []
    return [{"kind": "point_coordinate_wrong", "target": target, "expected_coords": list(expected), "actual_coords": list(actual)}]


def check_claim_geometry(kind: str, item: dict[str, Any], points: PointMap, source: str) -> list[dict[str, Any]]:
    if claim_was_removed(item, source):
        return []
    if kind == "foot_point":
        return _check_foot_point(item, points)
    if kind == "line_intersection":
        return _check_line_intersection(item, points)
    if kind == "points_collinear":
        return _check_points_collinear(item, points)
    if kind == "line_perpendicular":
        return _check_line_perpendicular(item, points)
    if kind == "angle_equals_degrees":
        return _check_angle_equals_degrees(item, points)
    if kind == "angle_equals_angle":
        return _check_angle_equals_angle(item, points)
    if kind == "length_equals_length":
        return _check_length_equals_length(item, points)
    return []


def _check_foot_point(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    target, source, line = str(item.get("target") or ""), str(item.get("source") or ""), point_pair(item.get("line"))
    if not target or not source or not line:
        return [{"kind": "foot_point_missing_expected", "target": target}]
    if target not in points or source not in points or line[0] not in points or line[1] not in points:
        return [{"kind": "point_not_found", "points": [target, source, *line]}]
    expected, actual = foot_point(points[source], points[line[0]], points[line[1]]), points[target]
    return [] if distance(actual, expected) <= 1e-3 else [{"kind": "foot_point_wrong", "target": target, "source": source, "line": list(line), "expected_coords": list(expected), "actual_coords": list(actual)}]


def _check_line_intersection(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    target, line_a, line_b = str(item.get("target") or ""), point_pair(item.get("line_a")), point_pair(item.get("line_b"))
    if not target or not line_a or not line_b:
        return [{"kind": "line_intersection_missing_expected", "target": target}]
    if target not in points or not all(name in points for name in (*line_a, *line_b)):
        return [{"kind": "point_not_found", "points": [target, *line_a, *line_b]}]
    expected = line_intersection(points[line_a[0]], points[line_a[1]], points[line_b[0]], points[line_b[1]])
    if expected is None:
        return [{"kind": "line_intersection_parallel", "line_a": list(line_a), "line_b": list(line_b)}]
    actual = points[target]
    return [] if distance(actual, expected) <= 1e-3 else [{"kind": "line_intersection_wrong", "target": target, "line_a": list(line_a), "line_b": list(line_b), "expected_coords": list(expected), "actual_coords": list(actual)}]


def _check_points_collinear(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    triple = point_triple(item.get("points"))
    if not triple:
        return [{"kind": "points_collinear_missing_expected"}]
    if not all(name in points for name in triple):
        return [{"kind": "point_not_found", "points": list(triple)}]
    dist = point_line_distance(points[triple[1]], points[triple[0]], points[triple[2]])
    return [] if dist <= 1e-3 else [{"kind": "points_not_collinear", "points": list(triple), "distance": dist}]


def _check_line_perpendicular(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    line_a, line_b = point_pair(item.get("line_a")), point_pair(item.get("line_b"))
    if not line_a or not line_b:
        return [{"kind": "line_perpendicular_missing_expected"}]
    if not all(name in points for name in (*line_a, *line_b)):
        return [{"kind": "point_not_found", "points": list((*line_a, *line_b))}]
    dot = sum(a * b for a, b in zip(vector(points[line_a[0]], points[line_a[1]]), vector(points[line_b[0]], points[line_b[1]]), strict=True))
    return [] if abs(dot) <= 1e-3 else [{"kind": "line_perpendicular_wrong", "line_a": list(line_a), "line_b": list(line_b), "dot": dot}]


def _check_angle_equals_degrees(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    angle_points, expected = point_triple(item.get("points")), number(item.get("expected_degrees"))
    if not angle_points or expected is None:
        return [{"kind": "angle_equals_degrees_missing_expected"}]
    if not all(name in points for name in angle_points):
        return [{"kind": "point_not_found", "points": list(angle_points)}]
    actual = angle_degrees(points[angle_points[0]], points[angle_points[1]], points[angle_points[2]])
    return [] if abs(actual - expected) <= 1.0 else [{"kind": "angle_equals_degrees_wrong", "points": list(angle_points), "expected_degrees": expected, "actual_degrees": actual}]


def _check_angle_equals_angle(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    angle_points, reference_points = point_triple(item.get("points")), point_triple(item.get("reference_points"))
    if not angle_points or not reference_points:
        return [{"kind": "angle_equals_angle_missing_expected"}]
    if not all(name in points for name in (*angle_points, *reference_points)):
        return [{"kind": "point_not_found", "points": list((*angle_points, *reference_points))}]
    actual = angle_degrees(points[angle_points[0]], points[angle_points[1]], points[angle_points[2]])
    expected = angle_degrees(points[reference_points[0]], points[reference_points[1]], points[reference_points[2]])
    return [] if abs(actual - expected) <= 1.0 else [{"kind": "angle_equals_angle_wrong", "points": list(angle_points), "reference_points": list(reference_points), "actual_degrees": actual, "reference_degrees": expected}]


def _check_length_equals_length(item: dict[str, Any], points: PointMap) -> list[dict[str, Any]]:
    segment_a, segment_b = point_pair(item.get("segment_a")), point_pair(item.get("segment_b"))
    if not segment_a or not segment_b:
        return [{"kind": "length_equals_length_missing_expected"}]
    if not all(name in points for name in (*segment_a, *segment_b)):
        return [{"kind": "point_not_found", "points": list((*segment_a, *segment_b))}]
    actual, expected = distance(points[segment_a[0]], points[segment_a[1]]), distance(points[segment_b[0]], points[segment_b[1]])
    return [] if abs(actual - expected) <= 1e-3 else [{"kind": "length_equals_length_wrong", "segment_a": list(segment_a), "segment_b": list(segment_b), "actual_length": actual, "reference_length": expected}]
