"""Small deterministic services for local smoke runs."""

from __future__ import annotations

import math
from collections.abc import Mapping
from fractions import Fraction

from manim_quality.geometry.numeric import (
    add,
    cross_norm,
    distance,
    dot,
    scale,
    subtract,
    vector,
)

from .models import CandidateAttempt, Finding, ValidationOutcome

TOLERANCE = 1e-9


class BasicRelationChecker:
    async def check(
        self, request: Mapping[str, object]
    ) -> Mapping[str, object]:
        relation = request.get("relation")
        operands = request.get("operands")
        if not isinstance(relation, str) or not isinstance(operands, list):
            raise ValueError("relation request is malformed")
        result = _evaluate_relation(relation, operands)
        if result is None:
            return {
                "verified": False,
                "holds": None,
                "reason": "unsupported_or_malformed_relation",
            }
        holds, residual = result
        return {
            "verified": True,
            "holds": holds,
            "residual": residual,
            "matches_expected": holds == request.get("expected"),
        }


class CompileOnlyValidator:
    async def validate(
        self,
        revision: CandidateAttempt,
        findings: tuple[Finding, ...],
        problem_hash: str,
    ) -> ValidationOutcome:
        del findings
        try:
            compile(revision.code, "candidate.py", "exec")
        except SyntaxError as error:
            return ValidationOutcome(
                passed=False,
                improved=False,
                summary=f"compile failed: {error.msg}",
                details={"compiled": False, "rendered": False},
                revision_id=revision.revision_id,
                code_hash=revision.code_hash,
                problem_hash=problem_hash,
            )
        return ValidationOutcome(
            passed=True,
            improved=True,
            summary="compile passed; full render was not run",
            details={"compiled": True, "rendered": False},
            revision_id=revision.revision_id,
            code_hash=revision.code_hash,
            problem_hash=problem_hash,
        )


class UnverifiedLayoutInspector:
    async def inspect(
        self,
        revision: CandidateAttempt,
        problem_hash: str,
    ) -> Mapping[str, object]:
        return {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "blocking_count": 0,
            "issues": [],
            "verified": False,
            "reason": "layout detector is not bound in compile-only smoke mode",
        }


def _evaluate_relation(
    relation: str, operands: list[object]
) -> tuple[bool, float] | None:
    if relation == "numeric_equal" and len(operands) == 2:
        if not all(_scalar(item) is not None for item in operands):
            return None
        left, right = (_scalar(item) for item in operands)
        assert left is not None and right is not None
        residual = abs(float(left - right))
        return residual <= TOLERANCE, residual
    if relation == "angle_degrees" and len(operands) == 4:
        return _angle_degrees(operands)
    points = [vector(item) for item in operands]
    if any(item is None for item in points):
        return None
    values = [item for item in points if item is not None]
    if relation in {"parallel", "perpendicular"} and len(values) == 2:
        return _vector_relation(relation, values[0], values[1])
    if relation == "collinear" and len(values) == 3:
        left = subtract(values[1], values[0])
        right = subtract(values[2], values[0])
        if left is None or right is None:
            return None
        residual = cross_norm(left, right)
        return None if residual is None else (residual <= TOLERANCE, residual)
    if relation == "midpoint" and len(values) == 3:
        total = add(values[1], values[2])
        if total is None:
            return None
        expected = scale(total, Fraction(1, 2))
        residual = distance(values[0], expected)
        return None if residual is None else (residual <= TOLERANCE, residual)
    if relation == "equal_length" and len(values) == 4:
        return _equal_scalars(
            distance(values[0], values[1]), distance(values[2], values[3])
        )
    if relation == "equal_distance" and len(values) == 3:
        return _equal_scalars(
            distance(values[0], values[1]), distance(values[0], values[2])
        )
    if relation == "point_on_segment" and len(values) == 3:
        return _point_on_segment(values[0], values[1], values[2])
    return None


_ANGLE_TOLERANCE_DEGREES = 0.1


def _angle_degrees(operands: list[object]) -> tuple[bool, float] | None:
    """[vertex, point_a, point_b, degrees]: angle at vertex between rays."""

    expected = _scalar(operands[3])
    corners = [vector(item) for item in operands[:3]]
    if expected is None or any(item is None for item in corners):
        return None
    vertex, first, second = corners
    left = subtract(first, vertex)
    right = subtract(second, vertex)
    if left is None or right is None:
        return None
    product = dot(left, right)
    lengths = [
        math.sqrt(sum(float(part) ** 2 for part in item)) for item in (left, right)
    ]
    if product is None or 0 in lengths:
        return None
    cosine = max(-1.0, min(1.0, float(product) / (lengths[0] * lengths[1])))
    actual = math.degrees(math.acos(cosine))
    residual = abs(actual - float(expected))
    return residual <= _ANGLE_TOLERANCE_DEGREES, residual


def _equal_scalars(left, right) -> tuple[bool, float] | None:
    if left is None or right is None:
        return None
    residual = abs(float(left) - float(right))
    return residual <= TOLERANCE, residual


def _point_on_segment(point, start, end) -> tuple[bool, float] | None:
    direct = distance(start, end)
    via = (
        None
        if (a := distance(start, point)) is None
        or (b := distance(point, end)) is None
        else a + b
    )
    if direct is None or via is None:
        return None
    residual = abs(float(via) - float(direct))
    return residual <= TOLERANCE, residual


def _vector_relation(relation: str, left, right) -> tuple[bool, float] | None:
    if relation == "parallel":
        residual = cross_norm(left, right)
    else:
        product = dot(left, right)
        residual = None if product is None else abs(float(product))
    return None if residual is None else (residual <= TOLERANCE, residual)


def _scalar(value: object) -> Fraction | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return Fraction(str(value))
