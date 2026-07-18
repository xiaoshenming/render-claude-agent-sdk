"""Formatting and compaction helpers for repair workdirs."""

from __future__ import annotations

import json
from typing import Any

COMPACT_OBJECT_FIELDS = ("path", "id", "name", "class", "kind", "text", "bbox")
COMPACT_BBOX_FIELDS = ("left", "right", "top", "bottom", "width", "height", "center_x", "center_y")


def _compact_issue(
    issue: Any,
    *,
    include_object_bbox: bool = True,
    object_ref_only: bool = False,
) -> dict[str, Any]:
    if not isinstance(issue, dict):
        return {"kind": "issue", "text": str(issue)}
    compact: dict[str, Any] = {}
    for key in _ISSUE_FIELDS:
        value = issue.get(key)
        if value is not None:
            compact[key] = _round_float(value)
    for key in ("a", "b"):
        value = issue.get(key)
        if value is None:
            value = issue.get(f"object_{key}")
        raw = issue.get(f"{key}_raw")
        source = raw if isinstance(raw, dict) else value
        if object_ref_only and isinstance(source, dict):
            compact[key] = _object_ref(source) or str(source)
        else:
            compact[key] = _compact_object(source, include_bbox=include_object_bbox)
    time_window = issue.get("time_window")
    if isinstance(time_window, dict):
        compact["time_window"] = {
            key: _round_float(time_window[key])
            for key in ("start", "end", "recommended_timestamp")
            if key in time_window
        }
    return compact


def _compact_object(obj: Any, *, include_bbox: bool = True) -> Any:
    if not isinstance(obj, dict):
        return obj
    compact: dict[str, Any] = {}
    for key in COMPACT_OBJECT_FIELDS:
        value = obj.get(key)
        if value is None or value == "":
            continue
        if key == "bbox" and isinstance(value, dict) and include_bbox:
            compact[key] = {
                field: _round_float(value[field])
                for field in COMPACT_BBOX_FIELDS
                if field in value
            }
        elif key != "bbox":
            compact[key] = _truncate_text(str(value)) if key == "text" else value
    ref = _object_ref(obj)
    if ref and not any(key in compact for key in ("path", "id", "name")):
        compact["ref"] = ref
    return compact or str(obj)


def _object_ref(obj: dict[str, Any]) -> str | None:
    for key in ("path", "id", "name"):
        value = obj.get(key)
        if value:
            return str(value)
    return None


def _round_float(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    return value


def _truncate_text(value: str, limit: int = 80) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _format_issue(issue: Any) -> str:
    if not isinstance(issue, dict):
        return str(issue)
    compact = _compact_issue(issue)
    kind = compact.get("kind", compact.get("type", compact.get("category", "issue")))
    a = compact.get("a", issue.get("object_a"))
    b = compact.get("b", issue.get("object_b"))
    if a is not None or b is not None:
        return f"{kind}: {_format_object_ref(a)} vs {_format_object_ref(b)}"
    return f"{kind}: {json.dumps(compact, ensure_ascii=False)}"


def _format_object_ref(obj: Any) -> str:
    if not isinstance(obj, dict):
        return str(obj)
    ref = obj.get("path") or obj.get("id") or obj.get("name") or obj.get("ref") or "unknown"
    label = obj.get("text") or obj.get("kind") or obj.get("class")
    return f"{ref} ({label})" if label else str(ref)


_ISSUE_FIELDS = (
    "kind",
    "type",
    "category",
    "step",
    "event",
    "ratio_of_smaller",
    "overlap_ratio",
    "x_overlap",
    "y_overlap",
    "target",
    "source",
    "line",
    "source_line",
    "points",
    "endpoints",
    "expected_coords",
    "actual_coords",
    "expected_degrees",
    "actual_degrees",
    "claim_text",
    "repair_hint",
    "suggested_replacement",
    "reason",
)
