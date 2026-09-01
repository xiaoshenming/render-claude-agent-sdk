"""Recover false-negative BBox facts into the existing compact pipeline."""

from __future__ import annotations

from collections.abc import Mapping

MIN_TEXT_RATIO = 0.08
TEXT_KINDS = frozenset({"text", "formula"})
CROSS_OWNER_SHAPES = frozenset({"Axes", "Arrow", "Line"})


def recover_candidates(probe: Mapping, payload: Mapping) -> dict[str, object]:
    issues = [dict(row) for row in payload.get("issues", [])
              if isinstance(row, Mapping)]
    seen = {_identity(row) for row in issues}
    recovered = []
    rows = [
        *list(probe.get("semantic_row_overlaps") or []),
        *list(probe.get("top_overlaps") or []),
        *list(probe.get("top_bounds_violations") or []),
    ]
    for row in rows:
        if not isinstance(row, Mapping) or not _recoverable(row):
            continue
        normalized = _normalize(row)
        if _identity(normalized) in seen:
            continue
        seen.add(_identity(normalized))
        recovered.append(normalized)
    combined = sorted(
        [*issues, *recovered], key=_score, reverse=True,
    )
    raw = dict(payload.get("raw") or {})
    raw["recovered_issue_count"] = len(recovered)
    return {**payload, "issues": combined, "blocking_count": len(combined),
            "passed": not combined, "raw": raw}


def _recoverable(row: Mapping) -> bool:
    category = str(row.get("category") or "")
    if category == "semantic_row_bbox_overlap":
        return _number(row.get("x_overlap")) > 0 and _number(row.get("y_overlap")) > 0
    if category == "text_formula_overlap":
        return _number(row.get("ratio_of_smaller")) >= MIN_TEXT_RATIO
    if category == "frame_bounds_overflow":
        item = row.get("object")
        return isinstance(item, Mapping) and str(item.get("kind")) in TEXT_KINDS
    if category != "label_shape_overlap_risk":
        return False
    pair = _text_shape_pair(row)
    if pair is None:
        return False
    text, shape = pair
    if str(shape.get("class")) == "Rectangle":
        return _number(row.get("x_overlap")) > 0 and _number(row.get("y_overlap")) > 0
    if (
        str(shape.get("class")) not in CROSS_OWNER_SHAPES
        or not isinstance(row.get("metadata"), Mapping)
        or not row["metadata"].get("near_collision")
        or _owner(text) == _owner(shape)
    ):
        return False
    compact = "".join(str(text.get("text") or "").split())
    return str(text.get("kind")) == "formula" or len(compact) >= 4


def _text_shape_pair(row: Mapping):
    values = [row.get("a"), row.get("b")]
    if not all(isinstance(value, Mapping) for value in values):
        return None
    first, second = values
    if str(first.get("kind")) in TEXT_KINDS and second.get("kind") == "shape":
        return first, second
    if str(second.get("kind")) in TEXT_KINDS and first.get("kind") == "shape":
        return second, first
    return None


def _normalize(row: Mapping) -> dict[str, object]:
    result = dict(row)
    for key in ("a", "b", "object"):
        value = result.get(key)
        if isinstance(value, Mapping):
            result[f"{key}_raw"] = dict(value)
            result[key] = str(value.get("path") or value.get("text") or "")
    result["recovered_from_raw_bbox"] = True
    return result


def _identity(row: Mapping) -> tuple[object, ...]:
    return (row.get("category"), _ref(row.get("a_raw") or row.get("a")),
            _ref(row.get("b_raw") or row.get("b")), row.get("step"), row.get("event"))


def _ref(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("path") or value.get("text") or "")
    return str(value or "")


def _owner(value: Mapping) -> str:
    parts = str(value.get("path") or "").split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else ".".join(parts)


def _score(row: Mapping) -> float:
    return max(_number(row.get("ratio_of_smaller")),
               _number(row.get("overflow_x")), _number(row.get("overflow_y")))


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
