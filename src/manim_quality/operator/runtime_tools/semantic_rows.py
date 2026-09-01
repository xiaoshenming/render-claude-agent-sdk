"""Preserve calculation-row identity for raw BBox evidence."""

from __future__ import annotations

from typing import Any

SEMANTIC_SOURCE = "_mathpi_bbox_semantic_source"
SEMANTIC_ROLE = "_mathpi_bbox_semantic_role"


def install_semantic_tagging(mobject_type) -> None:
    if getattr(mobject_type, "_mathpi_bbox_tagging_installed", False):
        return
    original_add = mobject_type.add

    def add(mob: Any, *items: Any):
        for item in items:
            _tag_calc_row(item)
        return original_add(mob, *items)

    mobject_type.add = add
    mobject_type._mathpi_bbox_tagging_installed = True


def collect_semantic_rows(scene: Any, delegate) -> list[dict[str, object]]:
    observed: dict[tuple[str, str], list[dict[str, float]]] = {}
    paths: dict[tuple[str, str], str] = {}
    seen = set()

    def walk(mob: Any, path: str) -> None:
        identity = id(mob)
        if identity in seen:
            return
        seen.add(identity)
        source = getattr(mob, SEMANTIC_SOURCE, None)
        if source is not None:
            bbox = delegate._bbox_of(mob)
            if bbox is not None:
                display = delegate._display_bbox_of(
                    scene, mob, bbox, prefer_bbox_corners=True,
                )
                key = (
                    _source_text(source),
                    str(getattr(mob, SEMANTIC_ROLE, "body")),
                )
                observed.setdefault(key, []).append(display or bbox)
                paths.setdefault(key, path)
        for index, child in enumerate(getattr(mob, "submobjects", ()) or ()):
            walk(child, f"{path}.{index}")

    for index, mob in enumerate(getattr(scene, "mobjects", ()) or ()):
        walk(mob, f"mobjects.{index}")
    return [
        {
            "path": paths[key],
            "kind": "formula",
            "class": "CalcRow",
            "text": key[0],
            "role": key[1],
            "bbox": _union_bbox(boxes),
        }
        for key, boxes in observed.items()
    ]


def semantic_row_overlaps(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    overlaps = []
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            x, y, ratio = _intersection(first["bbox"], second["bbox"])
            if ratio <= 0:
                continue
            overlaps.append({
                "category": "semantic_row_bbox_overlap",
                "ratio_of_smaller": ratio,
                "x_overlap": x,
                "y_overlap": y,
                "a": first,
                "b": second,
            })
    return sorted(
        overlaps, key=lambda item: item["ratio_of_smaller"], reverse=True,
    )


def dedupe_semantic(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    kept = []
    seen = set()
    for row in rows:
        identity = tuple(sorted((row["a"]["text"], row["b"]["text"])))
        if identity in seen:
            continue
        seen.add(identity)
        kept.append(row)
    return kept


def _tag_calc_row(mob: Any) -> None:
    source = getattr(mob, "_calc_source_content", None)
    if source is None:
        return
    role = str(getattr(mob, "_calc_role", "body"))
    for member in getattr(mob, "get_family", lambda: (mob,))():
        setattr(member, SEMANTIC_SOURCE, source)
        setattr(member, SEMANTIC_ROLE, role)


def _intersection(first: object, second: object) -> tuple[float, float, float]:
    if not isinstance(first, dict) or not isinstance(second, dict):
        return 0.0, 0.0, 0.0
    x = min(first["right"], second["right"]) - max(
        first["left"], second["left"])
    y = min(first["top"], second["top"]) - max(
        first["bottom"], second["bottom"])
    if x <= 0 or y <= 0:
        return 0.0, 0.0, 0.0
    smaller = min(first["width"] * first["height"],
                  second["width"] * second["height"])
    return round(x, 4), round(y, 4), round(x * y / smaller, 4)


def _source_text(value: object) -> str:
    if isinstance(value, (tuple, list)):
        return " ".join(str(item) for item in value if item is not None)[:240]
    return str(value)[:240]


def _union_bbox(boxes: list[dict[str, float]]) -> dict[str, float]:
    left = min(box["left"] for box in boxes)
    right = max(box["right"] for box in boxes)
    top = max(box["top"] for box in boxes)
    bottom = min(box["bottom"] for box in boxes)
    return {
        "left": round(left, 4),
        "right": round(right, 4),
        "top": round(top, 4),
        "bottom": round(bottom, 4),
        "width": round(right - left, 4),
        "height": round(top - bottom, 4),
        "center_x": round((left + right) / 2, 4),
        "center_y": round((top + bottom) / 2, 4),
    }
