"""Geometry and evidence helpers for layout repair brief generation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from libs.quality_repair.contract.workdir_format import _object_ref

ISSUE_KEYS = ("top_blocking_issues", "collisions", "blocking_pairs", "issues")
TEXTUAL_KINDS = {"text", "formula", "mathtex", "tex"}
TEXTUAL_CLASSES = {"Text", "MathTex", "Tex", "MarkupText", "Paragraph"}
SHAPE_KINDS = {"shape", "line", "polygon", "circle", "dot", "arrow"}
SHAPE_CLASSES = {"Line", "Polygon", "Circle", "Dot", "Arrow", "Arc", "Rectangle", "SurroundingRectangle"}


def looks_like_step_panel_lifecycle(issues: list[dict[str, Any]]) -> bool:
    if len(issues) < 6:
        return False
    regions = Counter(issue_region(issue) for issue in issues)
    right_share = regions.get("right_panel", 0) / len(issues)
    steps = {issue.get("step") for issue in issues if issue.get("step") is not None}
    texts = {object_text(obj) for issue in issues for obj in issue_objects(issue) if object_text(obj)}
    return right_share >= 0.55 and len(steps) >= 4 and len(texts) >= 6


def looks_like_same_origin_stack(issues: list[dict[str, Any]]) -> bool:
    if len(issues) < 3:
        return False
    steps = {issue.get("step") for issue in issues if issue.get("step") is not None}
    objects = {_object_ref(obj) or "" for issue in issues for obj in issue_objects(issue) if isinstance(obj, dict)}
    return len(steps) <= 2 and len([ref for ref in objects if ref]) >= 3


def is_label_shape_issue(issue: dict[str, Any]) -> bool:
    category = str(issue.get("category") or "").lower()
    return "label_shape" in category or (has_shape(issue) and has_textual(issue) and not is_textual_pair(issue))


def is_textual_pair(issue: dict[str, Any]) -> bool:
    objs = issue_objects(issue)
    return len(objs) >= 2 and all(is_textual(obj) for obj in objs[:2])


def has_textual(issue: dict[str, Any]) -> bool:
    return any(is_textual(obj) for obj in issue_objects(issue))


def has_shape(issue: dict[str, Any]) -> bool:
    return any(is_shape(obj) for obj in issue_objects(issue))


def is_textual(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    kind = str(obj.get("kind") or "").lower()
    cls = str(obj.get("class") or "")
    return kind in TEXTUAL_KINDS or cls in TEXTUAL_CLASSES or bool(obj.get("text"))


def is_shape(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    kind = str(obj.get("kind") or "").lower()
    cls = str(obj.get("class") or "")
    return kind in SHAPE_KINDS or cls in SHAPE_CLASSES


def same_center(issue: dict[str, Any]) -> bool:
    objs = issue_objects(issue)
    if len(objs) < 2:
        return False
    a = center(objs[0])
    b = center(objs[1])
    if not a or not b:
        return False
    return abs(a[0] - b[0]) <= 0.18 and abs(a[1] - b[1]) <= 0.16


def issue_region(issue: dict[str, Any]) -> str:
    centers = [item for item in (center(obj) for obj in issue_objects(issue)) if item]
    if not centers:
        return "unknown"
    x = sum(item[0] for item in centers) / len(centers)
    y = sum(item[1] for item in centers) / len(centers)
    if x >= 0.8:
        return "right_panel"
    if x <= -0.8:
        return "left_panel"
    if y >= 2.0:
        return "top_band"
    if y <= -2.0:
        return "bottom_band"
    return "center_panel"


def issue_objects(issue: dict[str, Any]) -> list[Any]:
    objects = []
    for key in ("a", "b", "object_a", "object_b", "a_raw", "b_raw"):
        value = issue.get(key)
        if value is not None:
            objects.append(value)
    return objects[:2]


def center(obj: Any) -> tuple[float, float] | None:
    if not isinstance(obj, dict):
        return None
    bbox = obj.get("bbox")
    if not isinstance(bbox, dict):
        return None
    try:
        return float(bbox["center_x"]), float(bbox["center_y"])
    except (KeyError, TypeError, ValueError):
        return None


def object_text(obj: Any) -> str:
    if not isinstance(obj, dict):
        return ""
    value = obj.get("text")
    return str(value) if value not in (None, "") else ""


def issue_ratio(issue: dict[str, Any]) -> float:
    for key in ("ratio_of_smaller", "overlap_ratio"):
        value = issue.get(key)
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def average_ratio(issues: list[dict[str, Any]]) -> float:
    if not issues:
        return 0.0
    return round(sum(issue_ratio(issue) for issue in issues) / len(issues), 4)


def time_window(issue: dict[str, Any]) -> dict[str, Any] | None:
    window = issue.get("time_window")
    if not isinstance(window, dict):
        return None
    return {key: window.get(key) for key in ("start", "end", "recommended_timestamp") if key in window}


def issues_from_context(layout_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ISSUE_KEYS:
        value = layout_ctx.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def blocking_count(layout_ctx: dict[str, Any], issues: list[dict[str, Any]]) -> int:
    for key in ("blocking_layout_issue_count", "blocking_count", "blocking"):
        value = layout_ctx.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return len(issues)


def share(counter: Counter[str]) -> float:
    total = sum(counter.values())
    if not total:
        return 0.0
    return round(counter.most_common(1)[0][1] / total, 4)


def estimated_tokens(byte_count: int | None) -> int | None:
    if byte_count is None:
        return None
    return max(1, round(byte_count / 4))


def file_size(path: Path | None) -> int | None:
    if not path:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def case_id_from_path(path: Path | None) -> str | None:
    if not path:
        return None
    if path.parent.name.startswith("overlap_"):
        return path.parent.parent.name
    return path.parent.name


def truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."
