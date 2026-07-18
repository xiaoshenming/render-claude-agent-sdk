"""Deterministic route-level logic contract templates."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .source_utils import clean


@dataclass(frozen=True)
class Point:
    x: float
    y: float


def route_contracts(source: str, manifest: dict[str, object]) -> tuple[list[dict[str, object]], list[str]]:
    route = str(manifest.get("route") or "")
    if "四边形 ACDB" in source or "最小周长" in source:
        return quadrilateral_contracts(source)
    if "BM+MN" in source and "AB=2√2" in source:
        return geometry_minimum_contracts()
    if route == "linear" or ("PA+PB" in source and "|PA-PB|" in source) or all(name in source for name in ("dot_P1", "dot_P2", "dot_P3", "dot_P4")):
        return four_point_linear_contracts(source)
    return [], ["no supported deterministic logic template matched"]


def four_point_linear_contracts(source: str) -> tuple[list[dict[str, object]], list[str]]:
    points = named_points(source)
    if "A" not in points or "B" not in points:
        return [], ["linear template matched but A/B coordinates were not found"]
    a = points["A"]
    b = points["B"]
    p1 = intersect_x(Point(a.x, -a.y), b)
    p2 = intersect_y(a, b)
    p3 = intersect_x(a, b)
    p4 = intersect_y(Point(-a.x, a.y), b)
    return [
        point_contract("dot_P1", p1, "(1) x-axis PA+PB min"),
        point_contract("dot_P2", p2, "(2) y-axis PA+PB min"),
        point_contract("dot_P3", p3, "(3) x-axis |PA-PB| max"),
        point_contract("dot_P4", p4, "(4) y-axis |PA-PB| max"),
    ], [f"A({a.x:g},{a.y:g}), B({b.x:g},{b.y:g}); generated four axis extrema contracts."]


def quadrilateral_contracts(source: str) -> tuple[list[dict[str, object]], list[str]]:
    points = sequential_ab_points(source)
    if not points:
        return [], ["quadrilateral template matched but A/B coordinates were not found"]
    a, b = points
    a_ref = Point(-a.x, a.y)
    b_ref = Point(b.x, -b.y)
    c = intersect_y(a_ref, b_ref)
    d = intersect_x(a_ref, b_ref)
    perimeter = sum_sqrt_text(distance_squared(a, b), distance_squared(a_ref, b_ref))
    return [
        point_contract("dot_C_opt", c, "C is A'B' intersection with y-axis"),
        point_contract("dot_D_opt", d, "D is A'B' intersection with x-axis"),
        {"kind": "source_contains", "text": perimeter, "label": "minimum perimeter"},
    ], [f"A'({-a.x:g},{a.y:g}), B'({b.x:g},{-b.y:g}); minimum perimeter {perimeter}."]


def geometry_minimum_contracts() -> tuple[list[dict[str, object]], list[str]]:
    return [
        {"kind": "source_contains", "text": "最小值为2", "label": "BM+MN final minimum"},
        {"kind": "source_not_contains", "text": "6\\sqrt{3}", "label": "do not use task 06 answer"},
        {"kind": "source_not_contains", "text": "6√3", "label": "do not use task 06 answer"},
    ], ["AB=2√2 and ∠BAC=45° template; expected BM+MN minimum is 2."]


def point_contract(target: str, point: Point, label: str) -> dict[str, object]:
    return {"kind": "point_coordinate", "target": target, "expected_coords": [clean(point.x), clean(point.y), 0.0], "label": label}


def named_points(source: str) -> dict[str, Point]:
    points: dict[str, Point] = {}
    for name, x, y in re.findall(r"([AB])\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)", source):
        points[name] = Point(float(x), float(y))
    seq = sequential_ab_points(source)
    if seq:
        points.setdefault("A", seq[0])
        points.setdefault("B", seq[1])
    return points


def sequential_ab_points(source: str) -> tuple[Point, Point] | None:
    match = re.search(
        r"A、B\s*的坐标分别是\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)，\((-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\)",
        source,
    )
    if not match:
        return None
    ax, ay, bx, by = (float(item) for item in match.groups())
    return Point(ax, ay), Point(bx, by)


def intersect_x(a: Point, b: Point) -> Point:
    t = -a.y / (b.y - a.y)
    return Point(a.x + t * (b.x - a.x), 0.0)


def intersect_y(a: Point, b: Point) -> Point:
    t = -a.x / (b.x - a.x)
    return Point(0.0, a.y + t * (b.y - a.y))


def distance_squared(a: Point, b: Point) -> int:
    return int(round((a.x - b.x) ** 2 + (a.y - b.y) ** 2))


def sum_sqrt_text(left_square: int, right_square: int) -> str:
    left_coeff, left_radical = sqrt_parts(left_square)
    right_coeff, right_radical = sqrt_parts(right_square)
    if left_radical == right_radical:
        coeff = left_coeff + right_coeff
        return f"{coeff}\\sqrt{{{left_radical}}}" if left_radical != 1 else str(coeff)
    return f"{sqrt_text(left_coeff, left_radical)}+{sqrt_text(right_coeff, right_radical)}"


def sqrt_parts(value: int) -> tuple[int, int]:
    coeff = 1
    radical = value
    factor = 2
    while factor * factor <= radical:
        while radical % (factor * factor) == 0:
            coeff *= factor
            radical //= factor * factor
        factor += 1
    return coeff, radical


def sqrt_text(coeff: int, radical: int) -> str:
    if radical == 1:
        return str(coeff)
    return f"{coeff}\\sqrt{{{radical}}}" if coeff != 1 else f"\\sqrt{{{radical}}}"
