"""Small exact-first vector primitives for geometry facts."""

from __future__ import annotations

import math
from collections.abc import Sequence
from fractions import Fraction

Scalar = Fraction
Vector = tuple[Scalar, ...]


def vector(value: object) -> Vector | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) not in {2, 3}:
        return None
    result: list[Fraction] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        if isinstance(item, float) and not math.isfinite(item):
            return None
        result.append(Fraction(str(item)))
    return tuple(result)


def subtract(left: Vector, right: Vector) -> Vector | None:
    if len(left) != len(right):
        return None
    return tuple(a - b for a, b in zip(left, right, strict=True))


def add(left: Vector, right: Vector) -> Vector | None:
    if len(left) != len(right):
        return None
    return tuple(a + b for a, b in zip(left, right, strict=True))


def scale(value: Vector, factor: Scalar) -> Vector:
    return tuple(item * factor for item in value)


def dot(left: Vector, right: Vector) -> Scalar | None:
    if len(left) != len(right):
        return None
    return sum((a * b for a, b in zip(left, right, strict=True)), Fraction())


def norm_squared(value: Vector) -> Scalar:
    return sum((item * item for item in value), Fraction())


def norm(value: Vector) -> float:
    return math.sqrt(float(norm_squared(value)))


def cross_norm(left: Vector, right: Vector) -> float | None:
    if len(left) != len(right):
        return None
    if len(left) == 2:
        return abs(float(left[0] * right[1] - left[1] * right[0]))
    cross = (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )
    return norm(cross)


def distance(left: Vector, right: Vector) -> float | None:
    delta = subtract(left, right)
    return norm(delta) if delta is not None else None
