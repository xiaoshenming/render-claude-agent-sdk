"""Versioned layout policy over frozen detector facts.

The frozen probe and checker report bbox-level collision facts. This policy
layer (QUALITY_PLATFORM.md section 5.5: raw facts layer vs versioned policy
layer) downgrades exactly one class of issue to a non-blocking warning: a
text/formula label whose bbox is fully contained in a shape's bbox while the
shape's real stroke segments provably stay outside a safety margin around the
label. Every decision is deterministic geometry over object roles and vertex
data from the geometry sidecar; missing or ambiguous evidence fails closed
and keeps the issue blocking.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

LAYOUT_POLICY_VERSION = "contained-label-v2"
POLICY_ID = "contained_label_no_stroke_contact"
STROKE_SAFETY_MARGIN = 0.08

_TEXT_KINDS = frozenset({"text", "formula"})

# Axis-aligned boxes are (left, right, bottom, top) in scene units.
_Box = tuple[float, float, float, float]
_Point = tuple[float, float]


def load_geometry_sidecar(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def evaluate_downgrade(
    issue: Mapping[str, object],
    sidecar: Mapping[str, object] | None,
) -> dict[str, object] | None:
    """Return the policy annotation when the issue is provably non-blocking."""
    pair = _text_shape_pair(issue)
    if pair is None or sidecar is None:
        return None
    text_box, shape = pair
    shape_box = _bbox(shape)
    if shape_box is None or not _contains(shape_box, text_box):
        return None
    geometries = _shape_geometries(sidecar, issue.get("step"), shape.get("path"))
    if not geometries:
        return None
    expanded = _expand(text_box, STROKE_SAFETY_MARGIN)
    for geometry in geometries:
        segments = _stroke_segments(geometry)
        if segments is None:
            return None
        if any(_segment_hits_rect(p, q, expanded) for p, q in segments):
            return None
    return {
        "id": POLICY_ID,
        "version": LAYOUT_POLICY_VERSION,
        "margin": STROKE_SAFETY_MARGIN,
        "reason": (
            "text bbox contained in shape bbox; every stroke segment stays "
            "outside the safety margin"
        ),
    }


def _text_shape_pair(
    issue: Mapping[str, object],
) -> tuple[_Box, Mapping[str, object]] | None:
    objects: list[Mapping[str, object]] = []
    for key in ("a", "b"):
        value = issue.get(f"{key}_raw") or issue.get(key)
        if not isinstance(value, Mapping):
            return None
        objects.append(value)
    kinds = [str(item.get("kind") or "") for item in objects]
    if kinds[0] in _TEXT_KINDS and kinds[1] == "shape":
        text_item, shape = objects
    elif kinds[1] in _TEXT_KINDS and kinds[0] == "shape":
        shape, text_item = objects
    else:
        return None
    text_box = _bbox(text_item)
    return None if text_box is None else (text_box, shape)


def _bbox(item: Mapping[str, object]) -> _Box | None:
    raw = item.get("bbox")
    if not isinstance(raw, Mapping):
        return None
    try:
        left, right = float(raw["left"]), float(raw["right"])
        bottom, top = float(raw["bottom"]), float(raw["top"])
    except (KeyError, TypeError, ValueError):
        return None
    if left > right or bottom > top:
        return None
    return (left, right, bottom, top)


def _contains(outer: _Box, inner: _Box) -> bool:
    return (
        outer[0] <= inner[0]
        and inner[1] <= outer[1]
        and outer[2] <= inner[2]
        and inner[3] <= outer[3]
    )


def _expand(box: _Box, margin: float) -> _Box:
    return (box[0] - margin, box[1] + margin, box[2] - margin, box[3] + margin)


def _shape_geometries(
    sidecar: Mapping[str, object],
    step: object,
    path: object,
) -> list[Mapping[str, object]]:
    captures = sidecar.get("captures")
    if not isinstance(captures, Sequence) or not isinstance(path, str) or not path:
        return []
    found: list[Mapping[str, object]] = []
    for capture in captures:
        if not isinstance(capture, Mapping) or capture.get("step") != step:
            continue
        shapes = capture.get("shapes")
        if not isinstance(shapes, Sequence):
            continue
        for shape in shapes:
            if not isinstance(shape, Mapping) or shape.get("path") != path:
                continue
            geometry = shape.get("geometry")
            if not isinstance(geometry, Mapping):
                return []  # ambiguous record for the matched shape: fail closed
            found.append(geometry)
    return found


def _stroke_segments(
    geometry: Mapping[str, object],
) -> list[tuple[_Point, _Point]] | None:
    raw = geometry.get("points")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    points: list[_Point] = []
    for value in raw:
        try:
            points.append((float(value[0]), float(value[1])))
        except (TypeError, ValueError, IndexError, KeyError):
            return None
    kind = str(geometry.get("type") or "")
    if kind in {"line", "polyline"} and len(points) >= 2:
        return list(zip(points, points[1:]))
    if kind == "polygon" and len(points) >= 3:
        return list(zip(points, points[1:] + points[:1]))
    return None


def _segment_hits_rect(p: _Point, q: _Point, box: _Box) -> bool:
    """Liang-Barsky clip: does segment p-q touch the axis-aligned box?"""
    left, right, bottom, top = box
    (x0, y0), (x1, y1) = p, q
    dx, dy = x1 - x0, y1 - y0
    t0, t1 = 0.0, 1.0
    for direction, distance in (
        (-dx, x0 - left),
        (dx, right - x0),
        (-dy, y0 - bottom),
        (dy, top - y0),
    ):
        if direction == 0.0:
            if distance < 0.0:
                return False
            continue
        ratio = distance / direction
        if direction < 0.0:
            t0 = max(t0, ratio)
        else:
            t1 = min(t1, ratio)
        if t0 > t1:
            return False
    return True
