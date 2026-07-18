from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SAFETY_MARGIN = 0.1


@dataclass(frozen=True, kw_only=True)
class BBox:
    name: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def area(self) -> float:
        return max(0.0, self.x_max - self.x_min) * max(0.0, self.y_max - self.y_min)

    @property
    def center_x(self) -> float:
        return (self.x_min + self.x_max) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    def shifted(self, *, axis: str, delta: float) -> "BBox":
        dx = delta if axis == "x" else 0.0
        dy = delta if axis != "x" else 0.0
        return BBox(
            name=self.name,
            x_min=self.x_min + dx,
            y_min=self.y_min + dy,
            x_max=self.x_max + dx,
            y_max=self.y_max + dy,
        )

    def within(self, safe: "BBox") -> bool:
        return self.x_min >= safe.x_min and self.x_max <= safe.x_max and self.y_min >= safe.y_min and self.y_max <= safe.y_max


@dataclass(frozen=True, kw_only=True)
class CollisionPair:
    a: str
    b: str


@dataclass(frozen=True, kw_only=True)
class SolverDecision:
    object_name: str
    action: str
    reason: str
    axis: str | None = None
    delta: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "object": self.object_name,
            "action": self.action,
            "reason": self.reason,
        }
        if self.axis is not None:
            payload["axis"] = self.axis
        if self.delta is not None:
            payload["delta"] = self.delta
        return payload


def _facts_path(facts_dir: Path, filename: str) -> Path:
    direct = facts_dir / filename
    nested = facts_dir / "facts" / filename
    return direct if direct.exists() else nested


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _bbox_from_list(name: str, value: list[Any]) -> BBox | None:
    if len(value) != 4:
        return None
    numbers = [_number(item) for item in value]
    if any(item is None for item in numbers):
        return None
    x_min, y_min, x_max, y_max = [float(item) for item in numbers]
    return BBox(name=name, x_min=x_min, y_min=y_min, x_max=x_max, y_max=y_max)


def _bbox_from_dict(name: str, value: dict[str, Any]) -> BBox | None:
    if "bbox" in value:
        return _parse_bbox(name, value["bbox"])
    if {"x_min", "y_min", "x_max", "y_max"}.issubset(value):
        raw = [value["x_min"], value["y_min"], value["x_max"], value["y_max"]]
        return _bbox_from_list(name, raw)
    if {"left", "right", "top", "bottom"}.issubset(value):
        left = _number(value["left"])
        right = _number(value["right"])
        top = _number(value["top"])
        bottom = _number(value["bottom"])
        if None in (left, right, top, bottom):
            return None
        return BBox(
            name=name,
            x_min=min(float(left), float(right)),
            y_min=min(float(top), float(bottom)),
            x_max=max(float(left), float(right)),
            y_max=max(float(top), float(bottom)),
        )
    return None


def _parse_bbox(name: str, value: Any) -> BBox | None:
    if isinstance(value, list):
        return _bbox_from_list(name, value)
    if isinstance(value, dict):
        return _bbox_from_dict(name, value)
    return None


def _parse_pairs(value: Any) -> list[CollisionPair] | None:
    if not isinstance(value, list):
        return None
    pairs: list[CollisionPair] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        a_name = item.get("a", item.get("object_a"))
        b_name = item.get("b", item.get("object_b"))
        if not isinstance(a_name, str) or not isinstance(b_name, str):
            return None
        pairs.append(CollisionPair(a=a_name, b=b_name))
    return pairs


def _parse_layout(value: Any) -> dict[str, BBox] | None:
    if not isinstance(value, dict):
        return None
    objects = value.get("objects", value.get("bboxes"))
    if isinstance(objects, dict):
        return _parse_layout_dict(objects)
    if isinstance(objects, list):
        return _parse_layout_list(objects)
    return None


def _parse_layout_dict(objects: dict[Any, Any]) -> dict[str, BBox] | None:
    parsed: dict[str, BBox] = {}
    for name, raw_bbox in objects.items():
        if not isinstance(name, str):
            return None
        bbox = _parse_bbox(name, raw_bbox)
        if bbox is None:
            return None
        parsed[name] = bbox
    return parsed


def _parse_layout_list(objects: list[Any]) -> dict[str, BBox] | None:
    parsed: dict[str, BBox] = {}
    for item in objects:
        if not isinstance(item, dict):
            return None
        name = item.get("name", item.get("object"))
        if not isinstance(name, str):
            return None
        bbox = _parse_bbox(name, item)
        if bbox is None:
            return None
        parsed[name] = bbox
    return parsed


def _parse_safe_area(value: Any) -> BBox | None:
    raw = value
    if isinstance(value, dict):
        raw = value.get("safe_area", value.get("bounds", value))
    return _parse_bbox("__safe_area__", raw)


def _load_facts(facts_dir: Path) -> tuple[list[CollisionPair], dict[str, BBox], BBox] | None:
    collisions = _read_json(_facts_path(facts_dir, "collisions.json"))
    layout = _read_json(_facts_path(facts_dir, "layout_context.json"))
    safe = _read_json(_facts_path(facts_dir, "safe_area.json"))
    pairs = _parse_pairs(collisions)
    boxes = _parse_layout(layout)
    safe_area = _parse_safe_area(safe)
    if pairs is None or boxes is None or safe_area is None:
        return None
    return pairs, boxes, safe_area


def _overlap(a_box: BBox, b_box: BBox, axis: str) -> float:
    if axis == "x":
        return min(a_box.x_max, b_box.x_max) - max(a_box.x_min, b_box.x_min)
    return min(a_box.y_max, b_box.y_max) - max(a_box.y_min, b_box.y_min)


def _delta(moving: BBox, fixed: BBox, *, axis: str, overlap: float) -> float:
    center = moving.center_x if axis == "x" else moving.center_y
    fixed_center = fixed.center_x if axis == "x" else fixed.center_y
    direction = -1.0 if center < fixed_center else 1.0
    return direction * (overlap + SAFETY_MARGIN)


def _reason(axis: str, delta: float, fixed: BBox, *, fallback: bool) -> str:
    direction = "left" if axis == "x" and delta < 0 else "right"
    if axis == "y":
        direction = "down" if delta < 0 else "up"
    prefix = "primary axis exceeded safe area; " if fallback else f"{axis} overlap smaller; "
    return f"{prefix}moving {direction} to avoid {fixed.name}"


def _choose_axis(overlap_x: float, overlap_y: float) -> str:
    return "x" if overlap_x <= overlap_y else "y"


def _solve_pair(a_box: BBox, b_box: BBox, safe_area: BBox) -> SolverDecision:
    moving, fixed = (a_box, b_box) if a_box.area <= b_box.area else (b_box, a_box)
    overlaps = {"x": _overlap(a_box, b_box, "x"), "y": _overlap(a_box, b_box, "y")}
    if overlaps["x"] <= 0 or overlaps["y"] <= 0:
        return SolverDecision(object_name=moving.name, action="skip", reason="no_overlap")
    primary = _choose_axis(overlaps["x"], overlaps["y"])
    for axis in (primary, "y" if primary == "x" else "x"):
        delta = _delta(moving, fixed, axis=axis, overlap=overlaps[axis])
        shifted = moving.shifted(axis=axis, delta=delta)
        if shifted.within(safe_area):
            return SolverDecision(
                object_name=moving.name,
                action="shift",
                axis=axis,
                delta=delta,
                reason=_reason(axis, delta, fixed, fallback=axis != primary),
            )
    return SolverDecision(object_name=moving.name, action="skip", reason="no_axial_solution")


class AxialSolver:
    def solve(self, facts_dir: Path) -> list[dict]:
        facts = _load_facts(facts_dir)
        if facts is None:
            return []
        pairs, boxes, safe_area = facts
        decisions: list[dict] = []
        current = dict(boxes)
        for pair in pairs:
            a_box = current.get(pair.a)
            b_box = current.get(pair.b)
            if a_box is None or b_box is None:
                return []
            decision = _solve_pair(a_box, b_box, safe_area)
            decisions.append(decision.to_dict())
            if decision.action == "shift" and decision.axis and decision.delta is not None:
                current[decision.object_name] = current[decision.object_name].shifted(
                    axis=decision.axis,
                    delta=decision.delta,
                )
        return decisions


def _cli_payload(argv: list[str] | None) -> list[dict]:
    parser = argparse.ArgumentParser(add_help=False, exit_on_error=False)
    parser.add_argument("--facts")
    args, _unknown = parser.parse_known_args(argv)
    if not args.facts:
        return []
    return AxialSolver().solve(Path(args.facts))


def main(argv: list[str] | None = None) -> None:
    try:
        payload = _cli_payload(argv)
    except BaseException:
        payload = []
    print(json.dumps(payload, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
