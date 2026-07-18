"""Small geometry helpers shared by contract generators."""

from __future__ import annotations

import math


Point3D = tuple[float, float, float]


def point_on_line(point: Point3D, a: Point3D, b: Point3D) -> bool:
    ab = (b[0] - a[0], b[1] - a[1])
    ap = (point[0] - a[0], point[1] - a[1])
    denom = math.hypot(*ab)
    if denom <= 1e-9:
        return False
    return abs(ab[0] * ap[1] - ab[1] * ap[0]) / denom <= 1e-3


def reflect_point(point: Point3D, a: Point3D, b: Point3D) -> Point3D:
    ab = (b[0] - a[0], b[1] - a[1])
    denom = ab[0] ** 2 + ab[1] ** 2
    if denom <= 1e-9:
        return point
    t = ((point[0] - a[0]) * ab[0] + (point[1] - a[1]) * ab[1]) / denom
    foot = (a[0] + t * ab[0], a[1] + t * ab[1])
    return (2 * foot[0] - point[0], 2 * foot[1] - point[1], point[2])


def angle_degrees(a: Point3D, vertex: Point3D, b: Point3D) -> float:
    va = (a[0] - vertex[0], a[1] - vertex[1])
    vb = (b[0] - vertex[0], b[1] - vertex[1])
    denom = math.hypot(*va) * math.hypot(*vb)
    if denom <= 1e-9:
        return 0.0
    cosine = max(-1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / denom))
    return math.degrees(math.acos(cosine))


def distance_tuple(left: Point3D, right: Point3D) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def segment_matches_points(actual: tuple[Point3D, Point3D], expected: tuple[Point3D, Point3D]) -> bool:
    return (
        distance_tuple(actual[0], expected[0]) <= 1e-3
        and distance_tuple(actual[1], expected[1]) <= 1e-3
    ) or (
        distance_tuple(actual[0], expected[1]) <= 1e-3
        and distance_tuple(actual[1], expected[0]) <= 1e-3
    )


def dot(a1: Point3D, a2: Point3D, b1: Point3D, b2: Point3D) -> float:
    va = (a2[0] - a1[0], a2[1] - a1[1])
    vb = (b2[0] - b1[0], b2[1] - b1[1])
    return va[0] * vb[0] + va[1] * vb[1]
