"""Preserve calculation-row identity for BBox classification."""

from __future__ import annotations

from typing import Any

SOURCE = "_mathpi_bbox_semantic_source"
ROLE = "_mathpi_bbox_semantic_role"


def install_tagging(mobject_type) -> None:
    if getattr(mobject_type, "_mathpi_bbox_tagging_installed", False):
        return
    original_add = mobject_type.add

    def add(mob: Any, *items: Any):
        for item in items:
            _tag(item)
        return original_add(mob, *items)

    mobject_type.add = add
    mobject_type._mathpi_bbox_tagging_installed = True


def collect(scene: Any, delegate) -> list[dict[str, object]]:
    boxes: dict[tuple[str, str], list[dict[str, float]]] = {}
    paths: dict[tuple[str, str], str] = {}
    seen = set()

    def walk(mob: Any, path: str) -> None:
        if id(mob) in seen:
            return
        seen.add(id(mob))
        source = getattr(mob, SOURCE, None)
        bbox = delegate._bbox_of(mob) if source is not None else None
        if bbox is not None:
            display = delegate._display_bbox_of(
                scene, mob, bbox, prefer_bbox_corners=True,
            )
            key = (_source_text(source), str(getattr(mob, ROLE, "body")))
            boxes.setdefault(key, []).append(display or bbox)
            paths.setdefault(key, path)
        for index, child in enumerate(getattr(mob, "submobjects", ()) or ()):
            walk(child, f"{path}.{index}")

    for index, mob in enumerate(getattr(scene, "mobjects", ()) or ()):
        walk(mob, f"mobjects.{index}")
    return [{
        "path": paths[key], "class": "CalcRow", "kind": "formula",
        "text": key[0], "role": key[1], "bbox": _union(value),
    } for key, value in boxes.items()]


def overlaps(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    found = []
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            x, y, ratio = _intersection(first["bbox"], second["bbox"])
            if ratio > 0:
                found.append({
                    "category": "semantic_row_bbox_overlap",
                    "ratio_of_smaller": ratio,
                    "x_overlap": x,
                    "y_overlap": y,
                    "a": first,
                    "b": second,
                })
    return sorted(found, key=lambda row: row["ratio_of_smaller"], reverse=True)


def dedupe(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    kept, seen = [], set()
    for row in rows:
        identity = tuple(sorted((row["a"]["text"], row["b"]["text"])))
        if identity not in seen:
            seen.add(identity)
            kept.append(row)
    return kept


def _tag(mob: Any) -> None:
    source = getattr(mob, "_calc_source_content", None)
    if source is None:
        return
    role = str(getattr(mob, "_calc_role", "body"))
    for member in getattr(mob, "get_family", lambda: (mob,))():
        setattr(member, SOURCE, source)
        setattr(member, ROLE, role)


def _source_text(value: object) -> str:
    if isinstance(value, (tuple, list)):
        return " ".join(str(item) for item in value if item is not None)[:240]
    return str(value)[:240]


def _intersection(first, second) -> tuple[float, float, float]:
    x = min(first["right"], second["right"]) - max(first["left"], second["left"])
    y = min(first["top"], second["top"]) - max(first["bottom"], second["bottom"])
    if x <= 0 or y <= 0:
        return 0.0, 0.0, 0.0
    smaller = min(first["width"] * first["height"],
                  second["width"] * second["height"])
    return round(x, 4), round(y, 4), round(x * y / smaller, 4)


def _union(boxes: list[dict[str, float]]) -> dict[str, float]:
    left, right = min(x["left"] for x in boxes), max(x["right"] for x in boxes)
    top, bottom = max(x["top"] for x in boxes), min(x["bottom"] for x in boxes)
    return {
        "left": round(left, 4), "right": round(right, 4),
        "top": round(top, 4), "bottom": round(bottom, 4),
        "width": round(right-left, 4), "height": round(top-bottom, 4),
        "center_x": round((left+right)/2, 4),
        "center_y": round((top+bottom)/2, 4),
    }
