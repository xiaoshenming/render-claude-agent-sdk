"""Geometry helpers for repairability classification."""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, kw_only=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True, kw_only=True)
class SafeArea:
    x_min: float
    x_max: float
    y_min: float
    y_max: float


def extract_expected_points(contract: Mapping[str, Any]) -> tuple[Point, ...]:
    if "expected_coords" in contract:
        return point_from_value(contract["expected_coords"])
    expected = contract.get("expected")
    if isinstance(expected, Mapping) and "coords" in expected:
        return point_from_value(expected["coords"])
    return ()


def within_safe_area(points: Sequence[Point], safe_area: SafeArea | None) -> bool:
    if safe_area is None or not points:
        return True
    return all(point_inside_margin(point, safe_area) for point in points)


def parse_safe_area(raw: dict[str, Any] | None) -> SafeArea | None:
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise TypeError("safe_area must be a mapping or None")
    return SafeArea(
        x_min=required_number(raw, "x_min"),
        x_max=required_number(raw, "x_max"),
        y_min=required_number(raw, "y_min"),
        y_max=required_number(raw, "y_max"),
    )


def contains_number(value: Any) -> bool:
    if is_number(value):
        return True
    if isinstance(value, Mapping):
        return any(contains_number(item) for item in value.values())
    if is_sequence(value):
        return any(contains_number(item) for item in value)
    return False


def point_from_value(value: Any) -> tuple[Point, ...]:
    if isinstance(value, Mapping):
        return point_from_mapping(value)
    if is_sequence(value) and len(value) >= 2:
        x_value, y_value = value[0], value[1]
        if is_number(x_value) and is_number(y_value):
            return (Point(x=float(x_value), y=float(y_value)),)
    return ()


def point_from_mapping(value: Mapping[str, Any]) -> tuple[Point, ...]:
    x_value = value.get("x")
    y_value = value.get("y")
    if is_number(x_value) and is_number(y_value):
        return (Point(x=float(x_value), y=float(y_value)),)
    return ()


def required_number(mapping: Mapping[str, Any], key: str) -> float:
    value = mapping.get(key)
    if not is_number(value):
        raise ValueError(f"safe_area.{key} must be numeric")
    return float(value)


def point_inside_margin(point: Point, safe_area: SafeArea) -> bool:
    x_min, x_max = expanded_bounds(safe_area.x_min, safe_area.x_max)
    y_min, y_max = expanded_bounds(safe_area.y_min, safe_area.y_max)
    return x_min <= point.x <= x_max and y_min <= point.y <= y_max


def expanded_bounds(lower: float, upper: float) -> tuple[float, float]:
    center = (lower + upper) / 2.0
    half_range = abs(upper - lower) / 2.0
    margin = half_range * 1.2
    return center - margin, center + margin


def is_number(value: Any) -> bool:
    return isinstance(value, Real) and not isinstance(value, bool)


def is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, bytes, bytearray, Sequence, Mapping, set, frozenset)):
        return len(value) > 0
    return bool(value)
