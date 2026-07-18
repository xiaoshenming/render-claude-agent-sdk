"""Suggested source replacements for logic-contract repairs."""

from __future__ import annotations

import re

from .geometry_math import Point3D
from .source_utils import NUM_RE, format_number, source_line


def point_on_line_suggested_replacement(source: str, line_no: int, target: str) -> str | None:
    line = source_line(source, line_no).strip()
    pattern = rf"({re.escape(target)}\s*=\s*)\((\w+)\s*\+\s*(\w+)\)\s*\*\s*({NUM_RE})\s*\+\s*(\w+)\s*\*\s*({NUM_RE})(.*)"
    match = re.match(pattern, line)
    if not match:
        return None
    prefix, left, right, first_weight_raw, extra_point, extra_weight_raw, suffix = match.groups()
    first_weight = float(first_weight_raw)
    extra_weight = float(extra_weight_raw)
    if extra_point == left and abs(first_weight + extra_weight - 1.0) <= 1e-6:
        return f"{prefix}{left} * {format_number(extra_weight)} + {right} * {format_number(first_weight)}{suffix}"
    if extra_point == right and abs(first_weight + extra_weight - 1.0) <= 1e-6:
        return f"{prefix}{left} * {format_number(first_weight)} + {right} * {format_number(extra_weight)}{suffix}"
    return None


def line_endpoint_suggested_replacement(target: str, expected: tuple[Point3D, Point3D]) -> str | None:
    left, right = expected
    dx = right[0] - left[0]
    if abs(dx) <= 1e-10:
        return None
    slope = (right[1] - left[1]) / dx
    intercept = left[1] - slope * left[0]
    x_min = min(left[0], right[0])
    x_max = max(left[0], right[0])
    return (
        f"{target} = self.make_line_by_formula("
        f"{format_number(slope)}, {format_number(intercept)}, "
        f"x_range=[{format_number(x_min)}, {format_number(x_max)}])"
    )


def array_assignment_suggested_replacement(target: str, coords: Point3D) -> str:
    return f"{target} = np.array([{format_number(coords[0])}, {format_number(coords[1])}, {format_number(coords[2])}])"


def angle_claim_suggested_replacement(claim_text: str) -> str:
    if "垂直平分" in claim_text and ("90°" in claim_text or "九十度" in claim_text):
        if claim_text.strip().startswith("角"):
            return "因为点在垂直平分线上，所以到线段两端点的距离相等。"
        return "点在垂直平分线上，到线段两端点距离相等"
    return claim_text.replace("90°", "").replace("九十度", "对应距离相等")
