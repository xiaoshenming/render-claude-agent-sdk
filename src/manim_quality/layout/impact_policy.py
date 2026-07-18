"""Severity and temporal policy for overlap observations."""

from __future__ import annotations

from typing import Any

POLICY_VERSION = "overlap-impact.v2"
MUST_REPAIR = "must_repair"
CONDITIONAL = "conditional_repair"
RECORD_ONLY = "record_only"


def classify_issue(issue: dict[str, Any]) -> tuple[str, str]:
    category = str(issue.get("category") or issue.get("kind") or "unknown")
    if category == "text_formula_overlap":
        if _formula_internal_structure(issue):
            return RECORD_ONLY, "formula_internal_structure"
        if _ratio(issue) >= 0.18 or _persistent(issue):
            return MUST_REPAIR, "visible_content_intersection"
        return RECORD_ONLY, "brief_or_small_content_contact"
    if category == "text_container_overflow":
        return MUST_REPAIR, "content_outside_container"
    if category == "frame_bounds_overflow":
        overflow = max(_number(issue.get("overflow_x")), _number(issue.get("overflow_y")))
        if overflow >= 0.08 or _persistent(issue):
            return MUST_REPAIR, "visible_frame_overflow"
        return RECORD_ONLY, "minor_frame_tolerance_contact"
    if category == "text_container_border_overlap":
        return RECORD_ONLY, "tight_container_padding"
    if category == "label_shape_overlap_risk":
        if _near_collision(issue):
            return RECORD_ONLY, "label_near_shape_without_intersection"
        if _short_geometric_annotation(issue) and _ratio(issue) < 0.6:
            return RECORD_ONLY, "intentional_short_geometric_annotation"
        if _ratio(issue) >= 0.18 and (_persistent(issue) or not _has_temporal_evidence(issue)):
            return CONDITIONAL, "persistent_label_shape_intersection"
        return RECORD_ONLY, "ambiguous_label_shape_contact"
    return RECORD_ONLY, "unclassified_observation"


def issue_summary(
    *, blocking: list[dict[str, Any]], warnings: list[dict[str, Any]], raw_count: int
) -> dict[str, Any]:
    all_records = [
        {"impact": item.get("impact", MUST_REPAIR), "issue": item}
        for item in blocking
    ] + list(warnings)
    categories: dict[str, int] = {}
    impacts = {MUST_REPAIR: 0, CONDITIONAL: 0, RECORD_ONLY: 0}
    for record in all_records:
        issue = record.get("issue") or {}
        category = str(issue.get("category") or issue.get("kind") or "unknown")
        categories[category] = categories.get(category, 0) + 1
        impact = str(record.get("impact") or RECORD_ONLY)
        impacts[impact] = impacts.get(impact, 0) + 1
    examples = []
    for record in all_records[:20]:
        issue = record.get("issue") or {}
        impact = str(record.get("impact") or issue.get("impact") or RECORD_ONLY)
        reason = str(issue.get("impact_reason") or record.get("reason") or "")
        examples.append(evidence_issue(issue, impact, reason))
    return {
        "policy_version": POLICY_VERSION,
        "raw_count": raw_count,
        "actionable_count": len(blocking),
        "record_only_count": len(warnings),
        "category_counts": categories,
        "impact_counts": impacts,
        "examples": examples,
    }


def evidence_issue(issue: dict[str, Any], impact: str, reason: str) -> dict[str, Any]:
    return {
        "category": str(issue.get("category") or issue.get("kind") or "unknown"),
        "impact": impact,
        "reason": reason,
        "scene": str(issue.get("scene") or "")[:160],
        "event": str(issue.get("event") or "")[:80],
        "time_window": issue.get("time_window") if isinstance(issue.get("time_window"), dict) else {},
        "occurrence_count": _integer(issue.get("occurrence_count"), 1),
        "observed_duration": round(_number(issue.get("observed_duration")), 4),
        "ratio_of_smaller": round(_ratio(issue), 4),
        "objects": [_object(item) for item in _objects(issue)[:2]],
    }


def _persistent(issue: dict[str, Any]) -> bool:
    return _integer(issue.get("occurrence_count"), 1) >= 2 or _duration(issue) >= 0.75


def _has_temporal_evidence(issue: dict[str, Any]) -> bool:
    return "occurrence_count" in issue or "observed_duration" in issue


def _duration(issue: dict[str, Any]) -> float:
    observed = _number(issue.get("observed_duration"))
    if observed > 0:
        return observed
    window = issue.get("time_window") or {}
    return max(0.0, _number(window.get("end")) - _number(window.get("start")))


def _near_collision(issue: dict[str, Any]) -> bool:
    metadata = issue.get("metadata") or {}
    return bool(metadata.get("near_collision"))


def _formula_internal_structure(issue: dict[str, Any]) -> bool:
    objects = _objects(issue)
    if len(objects) != 2 or not all(str(item.get("kind") or "") == "formula" for item in objects):
        return False
    first, second = (str(item.get("text") or "").replace(" ", "") for item in objects)
    if not first or not second:
        return False
    normalized = [
        value.replace("\\boxed{", "").rstrip("}")
        for value in (first, second)
    ]
    return normalized[0] == normalized[1]


def _short_geometric_annotation(issue: dict[str, Any]) -> bool:
    objects = _objects(issue)
    content = next(
        (item for item in objects if str(item.get("kind") or "") in {"text", "formula"}),
        None,
    )
    shape = next((item for item in objects if str(item.get("kind") or "") == "shape"), None)
    if not content or not shape:
        return False
    text = "".join(str(content.get("text") or "").split())
    shape_class = str(shape.get("class") or "")
    return 1 <= len(text) <= 8 and shape_class in {
        "Arrow",
        "DashedLine",
        "DoubleArrow",
        "Line",
        "TangentLine",
        "Vector",
    }


def _ratio(issue: dict[str, Any]) -> float:
    return _number(issue.get("ratio_of_smaller"))


def _objects(issue: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for key in ("a_raw", "b_raw", "object_raw", "a", "b", "object"):
        value = issue.get(key)
        if isinstance(value, dict) and value not in values:
            values.append(value)
    return values


def _object(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "class": str(value.get("class") or "")[:100],
        "kind": str(value.get("kind") or "")[:40],
        "text": str(value.get("text") or "")[:300],
        "bbox": value.get("bbox") if isinstance(value.get("bbox"), dict) else {},
    }


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
