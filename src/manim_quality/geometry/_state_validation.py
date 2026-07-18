"""Shape-specific validation for facts-only geometry state."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

_STATE_FIELDS = {
    "point": (frozenset({"position"}), frozenset()),
    "line": (frozenset({"start", "end"}), frozenset({"start_ref", "end_ref"})),
    "circle": (frozenset({"center", "radius"}), frozenset()),
    "polygon": (frozenset({"vertices"}), frozenset()),
}
_OBSERVED_FIELDS = {
    "collinear": frozenset({"normalized_cross"}),
    "equal_length": frozenset(
        {"left_length", "right_length", "relative_difference"}
    ),
    "line_endpoints": frozenset({"max_endpoint_distance", "orientation"}),
    "midpoint": frozenset({"normalized_midpoint_error"}),
    "parallel": frozenset({"normalized_cross"}),
    "perpendicular": frozenset({"normalized_dot_product"}),
    "point_on_circle": frozenset({"distance", "radius", "relative_difference"}),
    "point_on_line": frozenset({"normalized_cross", "scope"}),
}
_ALLOWED_ASSUMPTIONS = frozenset(
    {
        "checkpoint-scoped-observation",
        "dynamic-transforms-not-proven",
        "infinite-supporting-line",
        "scene-coordinate-space",
        "static-initial-state-only",
    }
)


def validate_object_state(
    kind: str, *, known: bool, state: Mapping[str, object]
) -> None:
    if not known:
        if state:
            raise ValueError("unknown geometry object state must be empty")
        return
    required, optional = _STATE_FIELDS[kind]
    keys = frozenset(state)
    if not required <= keys or not keys <= required | optional:
        raise ValueError(f"{kind} state fields do not match contract")
    _STATE_VALIDATORS[kind](state)


def validate_fact_content(
    relation: str,
    observed: Mapping[str, object],
    assumptions: Sequence[str],
) -> None:
    allowed = _OBSERVED_FIELDS.get(relation, frozenset())
    if not frozenset(observed) <= allowed:
        raise ValueError("geometry fact observed fields do not match relation")
    if any(item not in _ALLOWED_ASSUMPTIONS for item in assumptions):
        raise ValueError("geometry fact contains unsupported assumption")


def _same_dimensions(left: object, right: object, name: str) -> None:
    if _vector(left, name) != _vector(right, name):
        raise ValueError(f"{name} must use one coordinate dimension")


def _point_state(state: Mapping[str, object]) -> None:
    _vector(state["position"], "point position")


def _line_state(state: Mapping[str, object]) -> None:
    _same_dimensions(state["start"], state["end"], "line endpoints")
    for field in frozenset({"start_ref", "end_ref"}) & state.keys():
        if not isinstance(state[field], str) or not state[field].strip():
            raise ValueError(f"line {field} must be non-empty text")


def _circle_state(state: Mapping[str, object]) -> None:
    _vector(state["center"], "circle center")
    radius = state["radius"]
    if not _finite_number(radius) or radius <= 0:
        raise ValueError("circle radius must be positive and finite")


def _polygon_state(state: Mapping[str, object]) -> None:
    vertices = state["vertices"]
    if not isinstance(vertices, Sequence) or len(vertices) < 3:
        raise ValueError("polygon requires at least three vertices")
    dimensions = {_vector(item, "polygon vertex") for item in vertices}
    if len(dimensions) != 1:
        raise ValueError("polygon vertices must use one coordinate dimension")


def _vector(value: object, name: str) -> int:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) not in {2, 3}
        or any(not _finite_number(item) for item in value)
    ):
        raise ValueError(f"{name} must be a finite 2D or 3D vector")
    return len(value)


def _finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


_STATE_VALIDATORS = {
    "point": _point_state,
    "line": _line_state,
    "circle": _circle_state,
    "polygon": _polygon_state,
}
