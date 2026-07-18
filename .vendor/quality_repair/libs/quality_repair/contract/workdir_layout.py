"""Layout-context payload extraction for repair workdirs."""

from __future__ import annotations

from typing import Any

from .workdir_format import _compact_issue, _compact_object, _object_ref
from .workdir_normalize import COLLISION_KEYS, FACT_OBJECT_KEYS, _find_list_field

SAFE_AREA_KEYS = ("safe_area", "frame")
SAFE_AREA_FIELDS = ("x_min", "x_max", "y_min", "y_max")


def _audit_layout_context_for_agent(layout_ctx: dict[str, Any]) -> dict[str, Any]:
    issues = _find_list_field(layout_ctx, COLLISION_KEYS)
    active_objects = _active_visible_objects(layout_ctx, issues)
    blocking_count = _blocking_count(layout_ctx, issues)
    return {
        "active_visible_objects": [_compact_object(obj) for obj in active_objects],
        "blocking_layout_issue_count": blocking_count,
        "pass": bool(layout_ctx.get("pass", layout_ctx.get("passed", blocking_count == 0))),
        "status": str(layout_ctx.get("status") or ("pass" if blocking_count == 0 else "layout_failed")),
        "summary": str(layout_ctx.get("summary") or _audit_summary(issues, blocking_count)),
        "top_blocking_issues": [_compact_issue(issue) for issue in issues],
    }


def _active_visible_objects(layout_ctx: dict[str, Any], issues: list[Any]) -> list[dict[str, Any]]:
    active = layout_ctx.get("active_visible_objects")
    if isinstance(active, list):
        return [obj for obj in active if isinstance(obj, dict)]
    for key in FACT_OBJECT_KEYS:
        value = layout_ctx.get(key)
        if isinstance(value, list):
            return [obj for obj in value if isinstance(obj, dict)]
        if isinstance(value, dict):
            return [{"id": str(obj_id), **obj} for obj_id, obj in value.items() if isinstance(obj, dict)]
    return list(_layout_object_index(layout_ctx, issues).values())


def _blocking_count(layout_ctx: dict[str, Any], issues: list[Any]) -> int:
    for key in ("blocking_layout_issue_count", "blocking_count", "blocking"):
        value = layout_ctx.get(key)
        if value is not None and not isinstance(value, bool):
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return len(issues)


def _audit_summary(issues: list[Any], blocking_count: int) -> str:
    lines = [f"FAIL status=layout_failed blocking={blocking_count}" if blocking_count else "PASS status=pass blocking=0"]
    for index, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            lines.append(f"issue {index}: {issue}")
            continue
        compact = _compact_issue(issue)
        kind = compact.get("category", compact.get("kind", compact.get("type", "issue")))
        ratio = compact.get("ratio_of_smaller", compact.get("overlap_ratio", ""))
        a = _format_object_for_summary(compact.get("a"))
        b = _format_object_for_summary(compact.get("b"))
        lines.append(f"issue {index}: category={kind} step={compact.get('step', '')} ratio={ratio} a={a} b={b}")
    return "\n".join(lines)


def _format_object_for_summary(obj: Any) -> str:
    if not isinstance(obj, dict):
        return str(obj)
    ref = obj.get("path") or obj.get("id") or obj.get("name") or obj.get("ref") or "unknown"
    cls = obj.get("class", "")
    text = obj.get("text", "")
    return f"{ref}:{cls}:'{text}'"


def _compact_layout_context_for_agent(layout_ctx: dict[str, Any]) -> dict[str, Any]:
    issues = _find_list_field(layout_ctx, COLLISION_KEYS)
    compact_issues = [_compact_issue(issue, include_object_bbox=False, object_ref_only=True) for issue in issues]
    object_index = _layout_object_index(layout_ctx, issues)
    objects = {
        ref: _compact_object(object_index[ref])
        for ref in sorted(_issue_object_refs(compact_issues))
        if ref in object_index
    }
    payload: dict[str, Any] = {
        "schema_version": "quality_repair.layout_context.compact.v1",
        "blocking_count": len(issues),
        "issues": compact_issues,
    }
    safe_area = _find_safe_area(layout_ctx)
    if safe_area:
        payload["safe_area"] = safe_area
    if objects:
        payload["objects"] = objects
    return payload


def _layout_object_index(layout_ctx: dict[str, Any], issues: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for key in FACT_OBJECT_KEYS + ("active_visible_objects",):
        value = layout_ctx.get(key)
        _index_objects(value, index)
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        for key in ("a", "b", "a_raw", "b_raw", "object_a", "object_b"):
            obj = issue.get(key)
            if isinstance(obj, dict):
                object_ref = _object_ref(obj)
                if object_ref:
                    index.setdefault(object_ref, obj)
    return index


def _index_objects(value: Any, index: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, dict):
        for obj_id, obj in value.items():
            if isinstance(obj, dict):
                compact_source = {"id": obj_id, **obj}
                index[str(obj_id)] = compact_source
                object_ref = _object_ref(compact_source)
                if object_ref:
                    index.setdefault(object_ref, compact_source)
    elif isinstance(value, list):
        for obj in value:
            if isinstance(obj, dict):
                object_ref = _object_ref(obj)
                if object_ref:
                    index[object_ref] = obj


def _issue_object_refs(issues: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for issue in issues:
        for key in ("a", "b"):
            value = issue.get(key)
            if isinstance(value, dict):
                ref = _object_ref(value)
                if ref:
                    refs.add(ref)
            elif value is not None:
                refs.add(str(value))
    return refs


def _find_safe_area(layout_ctx: dict[str, Any]) -> dict[str, float] | None:
    for key in SAFE_AREA_KEYS:
        candidate = layout_ctx.get(key)
        if isinstance(candidate, dict) and all(f in candidate for f in SAFE_AREA_FIELDS):
            try:
                return {f: float(candidate[f]) for f in SAFE_AREA_FIELDS}
            except (TypeError, ValueError):
                continue
    return None
