"""Pure helpers for logic-contract validation."""

from __future__ import annotations

import math
import re
from typing import Any

TOLERANCE = 1e-4
LATEX_COMMAND_RE = re.compile(r"\\(?:dfrac|frac|text|implies|Rightarrow|therefore|because)")

Point3D = tuple[float, float, float]


def texts(item: dict[str, Any]) -> list[str]:
    value = item.get("text")
    if isinstance(value, str):
        return [value]
    values = item.get("texts")
    if isinstance(values, list):
        return [str(text) for text in values if isinstance(text, str)]
    return []


def source_has_text(source: str, text: str) -> bool:
    return text in source or text.replace("\\", "\\\\") in source


def point_pair(value: Any) -> tuple[str, str] | None:
    if isinstance(value, list | tuple) and len(value) >= 2:
        return (str(value[0]), str(value[1]))
    return None


def point_triple(value: Any) -> tuple[str, str, str] | None:
    if isinstance(value, list | tuple) and len(value) >= 3:
        return (str(value[0]), str(value[1]), str(value[2]))
    return None


def coords(value: Any) -> Point3D | None:
    if isinstance(value, list | tuple) and len(value) >= 2:
        x_value = number(value[0])
        y_value = number(value[1])
        z_value = number(value[2]) if len(value) > 2 else 0.0
        if x_value is not None and y_value is not None and z_value is not None:
            return (x_value, y_value, z_value)
    return None


def number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def distance(a: Point3D, b: Point3D) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def vector(a: Point3D, b: Point3D) -> Point3D:
    return tuple(right - left for left, right in zip(a, b, strict=True))  # type: ignore[return-value]


def close(left: float, right: float) -> bool:
    return abs(left - right) <= TOLERANCE


def point_line_distance(point: Point3D, a: Point3D, b: Point3D) -> float:
    ab = (b[0] - a[0], b[1] - a[1])
    ap = (point[0] - a[0], point[1] - a[1])
    denom = math.hypot(*ab)
    if denom <= TOLERANCE:
        return float("inf")
    return abs(ab[0] * ap[1] - ab[1] * ap[0]) / denom


def foot_point(point: Point3D, a: Point3D, b: Point3D) -> Point3D:
    ab = (b[0] - a[0], b[1] - a[1])
    denom = ab[0] ** 2 + ab[1] ** 2
    if denom <= TOLERANCE:
        return point
    t = ((point[0] - a[0]) * ab[0] + (point[1] - a[1]) * ab[1]) / denom
    return (a[0] + t * ab[0], a[1] + t * ab[1], point[2])


def line_intersection(a1: Point3D, a2: Point3D, b1: Point3D, b2: Point3D) -> Point3D | None:
    da = (a2[0] - a1[0], a2[1] - a1[1])
    db = (b2[0] - b1[0], b2[1] - b1[1])
    denom = da[0] * db[1] - da[1] * db[0]
    if abs(denom) <= TOLERANCE:
        return None
    delta = (b1[0] - a1[0], b1[1] - a1[1])
    t = (delta[0] * db[1] - delta[1] * db[0]) / denom
    return (a1[0] + t * da[0], a1[1] + t * da[1], a1[2])


def reflect_point(point: Point3D, a: Point3D, b: Point3D) -> Point3D:
    ab = (b[0] - a[0], b[1] - a[1])
    denom = ab[0] ** 2 + ab[1] ** 2
    if denom <= TOLERANCE:
        return point
    t = ((point[0] - a[0]) * ab[0] + (point[1] - a[1]) * ab[1]) / denom
    foot = (a[0] + t * ab[0], a[1] + t * ab[1])
    return (2 * foot[0] - point[0], 2 * foot[1] - point[1], point[2])


def angle_degrees(a: Point3D, vertex: Point3D, b: Point3D) -> float:
    va = (a[0] - vertex[0], a[1] - vertex[1])
    vb = (b[0] - vertex[0], b[1] - vertex[1])
    denom = math.hypot(*va) * math.hypot(*vb)
    if denom <= TOLERANCE:
        return 0.0
    cosine = max(-1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / denom))
    return math.degrees(math.acos(cosine))


def segment_matches_points(actual: tuple[Point3D, Point3D], expected: tuple[Point3D, Point3D]) -> bool:
    return (
        distance(actual[0], expected[0]) <= 1e-3
        and distance(actual[1], expected[1]) <= 1e-3
    ) or (
        distance(actual[0], expected[1]) <= 1e-3
        and distance(actual[1], expected[0]) <= 1e-3
    )


def line_has_unescaped_latex_command(line: str) -> bool:
    if not LATEX_COMMAND_RE.search(line):
        return False
    if "make_formula" in line or not re.search(r"[\u4e00-\u9fff]", line):
        return False
    return bool(re.search(r"(?<![A-Za-z])['\"][^'\"]*\\(?:dfrac|frac|text|implies|Rightarrow)", line))


def claim_was_removed(item: dict[str, Any], source: str) -> bool:
    claim_text = str(item.get("claim_text") or "")
    return bool(claim_text and not source_has_text(source, claim_text))
