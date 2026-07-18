"""Numeric comparison primitives for expected geometry relations."""

from __future__ import annotations

import math

from .schemas import ExpectedRelationClaim
from .symbolic_index import SymbolicGeometryIndex, SymbolicLine, Vector

TOLERANCE = 1e-6


def compare_numeric_relation(
    claim: ExpectedRelationClaim, index: SymbolicGeometryIndex
) -> tuple[bool | None, dict[str, object], tuple[int, ...]]:
    relation = claim.relation
    if relation in {"point_coordinate", "segment_length", "intersection"}:
        return _direct_relation(claim, index)
    if relation in {"parallel", "perpendicular", "equal_length"}:
        lines = tuple(index.resolve_segment(item) for item in claim.operands)
        if any(item is None for item in lines):
            return None, {}, ()
        left, right = lines
        assert left is not None and right is not None
        outcome, actual = _line_relation(relation, left, right)
        return outcome, actual, source_lines(index, left, right)
    if relation == "point_on_line":
        point = index.points.get(claim.operands[0])
        line = index.resolve_segment(claim.operands[1])
        if point is None or point.position is None or line is None:
            return None, {}, ()
        residual = _cross_residual(_vector(line), _subtract(point.position, line.start))
        return (
            residual <= TOLERANCE,
            {"normalized_cross": residual},
            unique_lines(point.line_start, *source_lines(index, line)),
        )
    points = tuple(index.points.get(item) for item in claim.operands)
    if any(item is None or item.position is None for item in points):
        return None, {}, ()
    values = tuple(item.position for item in points if item is not None)
    lines = unique_lines(*(item.line_start for item in points if item is not None))
    if relation == "collinear":
        residual = _cross_residual(
            _subtract(values[1], values[0]), _subtract(values[2], values[0])
        )
        return residual <= TOLERANCE, {"normalized_cross": residual}, lines
    if relation == "midpoint":
        expected = tuple(
            (a + b) / 2 for a, b in zip(values[1], values[2], strict=True)
        )
        residual = _distance(values[0], expected) / max(
            _distance(values[1], values[2]), TOLERANCE
        )
        return residual <= TOLERANCE, {"normalized_midpoint_error": residual}, lines
    return None, {}, ()


def unique_lines(*values: int) -> tuple[int, ...]:
    return tuple(sorted(set(values)))


def source_lines(
    index: SymbolicGeometryIndex, *lines: SymbolicLine
) -> tuple[int, ...]:
    values: list[int] = []
    for line in lines:
        values.append(line.line_start)
        for ref in (line.start_ref, line.end_ref):
            point = index.points.get(ref or "")
            if point is not None:
                values.append(point.line_start)
    return unique_lines(*values)


def _direct_relation(
    claim: ExpectedRelationClaim, index: SymbolicGeometryIndex
) -> tuple[bool | None, dict[str, object], tuple[int, ...]]:
    if claim.relation == "point_coordinate":
        point = index.points.get(claim.operands[0])
        if point is None or point.position is None:
            return None, {}, ()
        expected = tuple(float(value) for value in claim.operands[1:])
        distance = _distance(point.position, expected)
        return (
            distance <= TOLERANCE,
            {"position": point.position, "expected": expected, "distance": distance},
            (point.line_start,),
        )
    if claim.relation == "segment_length":
        line = index.resolve_segment(claim.operands[0])
        if line is None:
            return None, {}, ()
        expected = float(claim.operands[1])
        actual = _norm(_vector(line))
        relative_error = abs(actual - expected) / max(abs(expected), TOLERANCE)
        return (
            relative_error <= TOLERANCE,
            {"length": actual, "expected": expected, "relative_error": relative_error},
            source_lines(index, line),
        )
    return _intersection(claim, index)


def _intersection(
    claim: ExpectedRelationClaim, index: SymbolicGeometryIndex
) -> tuple[bool | None, dict[str, object], tuple[int, ...]]:
    point = index.points.get(claim.operands[0])
    left = index.resolve_segment(claim.operands[1])
    right = index.resolve_segment(claim.operands[2])
    if point is None or point.position is None or left is None or right is None:
        return None, {}, ()
    left_residual = _cross_residual(
        _vector(left), _subtract(point.position, left.start)
    )
    right_residual = _cross_residual(
        _vector(right), _subtract(point.position, right.start)
    )
    return (
        max(left_residual, right_residual) <= TOLERANCE,
        {
            "line_1_normalized_cross": left_residual,
            "line_2_normalized_cross": right_residual,
        },
        unique_lines(point.line_start, *source_lines(index, left, right)),
    )


def _line_relation(
    relation: str, left: SymbolicLine, right: SymbolicLine
) -> tuple[bool, dict[str, object]]:
    left_vector, right_vector = _vector(left), _vector(right)
    if relation == "parallel":
        residual = _cross_residual(left_vector, right_vector)
        return residual <= TOLERANCE, {"normalized_cross": residual}
    if relation == "perpendicular":
        residual = abs(_dot(left_vector, right_vector)) / (
            _norm(left_vector) * _norm(right_vector)
        )
        return residual <= TOLERANCE, {"normalized_dot_product": residual}
    left_length, right_length = _norm(left_vector), _norm(right_vector)
    residual = abs(left_length - right_length) / max(left_length, right_length)
    return residual <= TOLERANCE, {"relative_difference": residual}


def _vector(line: SymbolicLine) -> Vector:
    assert line.start is not None and line.end is not None
    return _subtract(line.end, line.start)


def _subtract(left: Vector, right: Vector | None) -> Vector:
    assert right is not None
    return tuple(a - b for a, b in zip(left, right, strict=True))


def _dot(left: Vector, right: Vector) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _norm(value: Vector) -> float:
    return math.sqrt(_dot(value, value))


def _distance(left: Vector, right: Vector) -> float:
    return _norm(_subtract(left, right))


def _cross_residual(left: Vector, right: Vector) -> float:
    denominator = _norm(left) * _norm(right)
    if denominator == 0:
        return math.inf
    x1, y1 = left[:2]
    x2, y2 = right[:2]
    return abs(x1 * y2 - y1 * x2) / denominator
