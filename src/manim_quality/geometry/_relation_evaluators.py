"""Pure evaluators used by the public geometry relation dispatcher."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from fractions import Fraction

from .numeric import (
    Vector,
    add,
    cross_norm,
    distance,
    dot,
    norm,
    norm_squared,
    scale,
    subtract,
    vector,
)
from .schemas import GeometryObject

FALSE_MULTIPLIER = 10.0
Evaluator = Callable[
    [tuple[GeometryObject, ...], float], tuple[object, dict[str, object]]
]


def parallel(objects: tuple[GeometryObject, ...], tolerance: float):
    vectors = _line_vectors(objects)
    if vectors is None:
        return "unsupported_object", {}
    return _vector_parallel(*vectors, tolerance)


def perpendicular(objects: tuple[GeometryObject, ...], tolerance: float):
    vectors = _line_vectors(objects)
    if vectors is None:
        return "unsupported_object", {}
    left, right = vectors
    denominator = norm(left) * norm(right)
    product = dot(left, right)
    if denominator == 0 or product is None:
        return "ambiguous_space", {}
    residual = abs(float(product)) / denominator
    return _zero_decision(residual, tolerance), {"normalized_dot_product": residual}


def equal_length(objects: tuple[GeometryObject, ...], tolerance: float):
    vectors = _line_vectors(objects)
    if vectors is None:
        return "unsupported_object", {}
    left, right = vectors
    left_sq, right_sq = norm_squared(left), norm_squared(right)
    if left_sq == 0 or right_sq == 0:
        return "ambiguous_space", {}
    left_length, right_length = norm(left), norm(right)
    residual = abs(left_length - right_length) / max(left_length, right_length)
    return _zero_decision(residual, tolerance), {
        "left_length": left_length,
        "right_length": right_length,
        "relative_difference": residual,
    }


def collinear(objects: tuple[GeometryObject, ...], tolerance: float):
    points = _points(objects)
    if points is None:
        return "unsupported_object", {}
    left = subtract(points[1], points[0])
    right = subtract(points[2], points[0])
    if left is None or right is None:
        return "ambiguous_space", {}
    return _vector_parallel(left, right, tolerance)


def point_on_line(objects: tuple[GeometryObject, ...], tolerance: float):
    if objects[0].kind != "point" or objects[1].kind != "line":
        return "unsupported_object", {}
    point_value = _state_vector(objects[0], "position")
    endpoints = _line_endpoints(objects[1])
    if point_value is None or endpoints is None:
        return "unsupported_object", {}
    direction = subtract(endpoints[1], endpoints[0])
    offset = subtract(point_value, endpoints[0])
    if direction is None or offset is None:
        return "ambiguous_space", {}
    outcome, observed = _vector_parallel(direction, offset, tolerance)
    observed["scope"] = "infinite_line"
    return outcome, observed


def point_on_circle(objects: tuple[GeometryObject, ...], tolerance: float):
    if objects[0].kind != "point" or objects[1].kind != "circle":
        return "unsupported_object", {}
    point_value = _state_vector(objects[0], "position")
    center = _state_vector(objects[1], "center")
    radius = _positive_scalar(objects[1].state.get("radius"))
    if point_value is None or center is None or radius is None:
        return "unsupported_object", {}
    delta = subtract(point_value, center)
    if delta is None:
        return "ambiguous_space", {}
    distance_sq = norm_squared(delta)
    if distance_sq == radius * radius:
        return True, {
            "distance": math.sqrt(float(distance_sq)),
            "radius": float(radius),
        }
    actual = math.sqrt(float(distance_sq))
    residual = abs(actual - float(radius)) / max(float(radius), 1.0)
    return _zero_decision(residual, tolerance), {
        "distance": actual,
        "radius": float(radius),
        "relative_difference": residual,
    }


def midpoint(objects: tuple[GeometryObject, ...], tolerance: float):
    points = _points(objects)
    if points is None:
        return "unsupported_object", {}
    total = add(points[1], points[2])
    if total is None:
        return "ambiguous_space", {}
    expected = scale(total, Fraction(1, 2))
    residual = distance(points[0], expected)
    span = distance(points[1], points[2])
    if residual is None or span is None or span == 0:
        return "ambiguous_space", {}
    normalized = residual / span
    return _zero_decision(normalized, tolerance), {
        "normalized_midpoint_error": normalized
    }


def line_endpoints(objects: tuple[GeometryObject, ...], tolerance: float):
    if objects[0].kind != "line":
        return "unsupported_object", {}
    points = _points(objects[1:])
    endpoints = _line_endpoints(objects[0])
    if points is None or endpoints is None:
        return "unsupported_object", {}
    direct = _endpoint_residual(endpoints, points)
    reverse = _endpoint_residual(endpoints, (points[1], points[0]))
    residual = min(direct, reverse)
    return _zero_decision(residual, tolerance), {
        "max_endpoint_distance": residual,
        "orientation": "direct" if direct <= reverse else "reverse",
    }


def _line_vectors(objects: tuple[GeometryObject, ...]):
    if len(objects) != 2 or any(item.kind != "line" for item in objects):
        return None
    endpoints = tuple(_line_endpoints(item) for item in objects)
    if any(item is None for item in endpoints):
        return None
    first, second = endpoints
    assert first is not None and second is not None
    left = subtract(first[1], first[0])
    right = subtract(second[1], second[0])
    return (left, right) if left is not None and right is not None else None


def _line_endpoints(item: GeometryObject):
    start = _state_vector(item, "start")
    end = _state_vector(item, "end")
    return (start, end) if start is not None and end is not None else None


def _points(objects: Sequence[GeometryObject]):
    if any(item.kind != "point" for item in objects):
        return None
    values = tuple(_state_vector(item, "position") for item in objects)
    if any(item is None for item in values):
        return None
    return tuple(item for item in values if item is not None)


def _state_vector(item: GeometryObject, field: str):
    return vector(item.state.get(field))


def _positive_scalar(value: object):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    result = Fraction(str(value))
    return result if result > 0 else None


def _vector_parallel(left: Vector, right: Vector, tolerance: float):
    denominator = norm(left) * norm(right)
    if denominator == 0:
        return "ambiguous_space", {}
    cross = cross_norm(left, right)
    if cross is None:
        return "ambiguous_space", {}
    residual = cross / denominator
    return _zero_decision(residual, tolerance), {"normalized_cross": residual}


def _zero_decision(residual: float, tolerance: float):
    if residual <= tolerance:
        return True
    if residual >= tolerance * FALSE_MULTIPLIER:
        return False
    return "ambiguous_space"


def _endpoint_residual(actual, expected) -> float:
    distances = (
        distance(actual[0], expected[0]),
        distance(actual[1], expected[1]),
    )
    if any(item is None for item in distances):
        return math.inf
    return max(item for item in distances if item is not None)


EVALUATORS: dict[str, Evaluator] = {
    "collinear": collinear,
    "equal_length": equal_length,
    "line_endpoints": line_endpoints,
    "midpoint": midpoint,
    "parallel": parallel,
    "perpendicular": perpendicular,
    "point_on_circle": point_on_circle,
    "point_on_line": point_on_line,
}
_THREE_OPERAND_RELATIONS = frozenset({"collinear", "line_endpoints", "midpoint"})
OPERAND_COUNTS = {
    name: 3 if name in _THREE_OPERAND_RELATIONS else 2 for name in EVALUATORS
}
