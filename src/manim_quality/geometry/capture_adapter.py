"""Convert renderer observations into versioned geometry snapshots."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from numbers import Real

from .schemas import SNAPSHOT_SCHEMA_VERSION, GeometrySnapshot, parse_geometry_snapshot


@dataclass(frozen=True, slots=True)
class RuntimeObservation:
    """A renderer-owned object and its stable source identity."""

    object_id: str
    kind: str
    value: object
    source: Mapping[str, object]


def capture_runtime_snapshot(
    *,
    code_hash: str,
    scene_id: str,
    checkpoint_id: str,
    observations: Sequence[RuntimeObservation],
    final: bool = False,
) -> GeometrySnapshot:
    """Capture supported geometry without importing or depending on Manim."""

    objects = [_capture_observation(item) for item in observations]
    return parse_geometry_snapshot(
        {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "code_hash": code_hash,
            "scene_id": scene_id,
            "checkpoint_id": checkpoint_id,
            "provenance": "runtime_final" if final else "runtime_checkpoint",
            "objects": objects,
        }
    )


def _capture_observation(observation: RuntimeObservation) -> dict[str, object]:
    try:
        state = _STATE_READERS[observation.kind](observation.value)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return _wire_object(observation, status="unknown", reason="unsupported_object")
    return _wire_object(observation, status="known", state=state)


def _wire_object(
    observation: RuntimeObservation,
    *,
    status: str,
    state: Mapping[str, object] | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    return {
        "object_id": observation.object_id,
        "kind": observation.kind,
        "status": status,
        "reason_code": reason,
        "state": dict(state or {}),
        "source": dict(observation.source),
    }


def _point(value: object) -> dict[str, object]:
    return {"position": _vector(_call(value, "get_center"))}


def _line(value: object) -> dict[str, object]:
    return {
        "start": _vector(_call(value, "get_start")),
        "end": _vector(_call(value, "get_end")),
    }


def _circle(value: object) -> dict[str, object]:
    radius = value.radius  # type: ignore[attr-defined]
    return {"center": _vector(_call(value, "get_center")), "radius": _number(radius)}


def _polygon(value: object) -> dict[str, object]:
    vertices = _sequence(_call(value, "get_vertices"))
    if len(vertices) < 3:
        raise ValueError("polygon requires at least three vertices")
    return {"vertices": [_vector(vertex) for vertex in vertices]}


def _call(value: object, accessor: str) -> object:
    method = getattr(value, accessor)
    if not callable(method):
        raise TypeError(f"{accessor} is not callable")
    return method()


def _vector(value: object) -> list[int | float]:
    items = _sequence(value)
    if len(items) not in (2, 3):
        raise ValueError("geometry vector must have two or three dimensions")
    return [_number(item) for item in items]


def _sequence(value: object) -> Sequence[object]:
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        value = tolist()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    raise TypeError("geometry value must be a sequence")


def _number(value: object) -> int | float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("geometry coordinate must be numeric")
    result = int(value) if isinstance(value, int) else float(value)
    if not math.isfinite(result):
        raise ValueError("geometry coordinate must be finite")
    return result


_STATE_READERS: Mapping[str, Callable[[object], dict[str, object]]] = {
    "point": _point,
    "line": _line,
    "circle": _circle,
    "polygon": _polygon,
}
