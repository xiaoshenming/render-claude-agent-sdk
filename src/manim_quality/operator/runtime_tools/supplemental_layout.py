"""Restore high-signal layout facts filtered by the frozen vendor checker."""

from __future__ import annotations

from collections.abc import Mapping

MIN_TEXT_OVERLAP_RATIO = 0.08
_TEXT_KINDS = frozenset({"text", "formula"})
_CROSS_OWNER_SHAPES = frozenset({"Axes", "Arrow", "Line"})


def merge_supplemental_issues(
    probe: Mapping[str, object],
    detector: Mapping[str, object],
) -> dict[str, object]:
    result = dict(detector)
    issues = [
        dict(row) for row in detector.get("issues", []) if isinstance(row, Mapping)
    ]
    identities = {_identity(row) for row in issues}
    added = []
    raw_rows = [
        *list(probe.get("top_overlaps") or []),
        *list(probe.get("top_bounds_violations") or []),
    ]
    for row in raw_rows:
        if not isinstance(row, Mapping) or not _is_high_signal(row):
            continue
        normalized = _normalize(row)
        identity = _identity(normalized)
        if identity in identities:
            continue
        identities.add(identity)
        issues.append(normalized)
        added.append(normalized)
    raw = dict(result.get("raw") or {})
    raw["supplemental_issue_count"] = len(added)
    raw["supplemental_policy_version"] = "layout-supplement-v1"
    result.update(
        issues=issues,
        blocking_count=len(issues),
        passed=not issues,
        raw=raw,
    )
    return result


def _is_high_signal(issue: Mapping[str, object]) -> bool:
    category = str(issue.get("category") or "")
    if category == "text_formula_overlap":
        return _number(issue.get("ratio_of_smaller")) >= MIN_TEXT_OVERLAP_RATIO
    if category == "frame_bounds_overflow":
        item = issue.get("object")
        return (
            isinstance(item, Mapping)
            and str(item.get("kind") or "") in _TEXT_KINDS
            and max(_number(issue.get("overflow_x")), _number(issue.get("overflow_y")))
            > 0
        )
    return category == "label_shape_overlap_risk" and _cross_owner_near_collision(issue)


def _cross_owner_near_collision(issue: Mapping[str, object]) -> bool:
    metadata = issue.get("metadata")
    if not isinstance(metadata, Mapping) or not metadata.get("near_collision"):
        return False
    pair = _text_shape_pair(issue)
    if pair is None:
        return False
    content, shape = pair
    if str(shape.get("class") or "") not in _CROSS_OWNER_SHAPES:
        return False
    if _owner(content) == _owner(shape):
        return False
    text = "".join(str(content.get("text") or "").split())
    return str(content.get("kind") or "") == "formula" or len(text) >= 4


def _text_shape_pair(
    issue: Mapping[str, object],
) -> tuple[Mapping[str, object], Mapping[str, object]] | None:
    values = [issue.get("a"), issue.get("b")]
    if not all(isinstance(value, Mapping) for value in values):
        return None
    first, second = values
    if str(first.get("kind") or "") in _TEXT_KINDS and second.get("kind") == "shape":
        return first, second
    if str(second.get("kind") or "") in _TEXT_KINDS and first.get("kind") == "shape":
        return second, first
    return None


def _normalize(issue: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(issue)
    if "a" not in normalized and isinstance(normalized.get("object"), Mapping):
        normalized["a"] = normalized["object"]
    for key in ("a", "b", "object"):
        value = normalized.get(key)
        if not isinstance(value, Mapping):
            continue
        normalized[f"{key}_raw"] = dict(value)
        normalized[key] = _object_ref(value)
    normalized["supplemental_reason"] = "restored_high_signal_filtered_fact"
    return normalized


def _identity(issue: Mapping[str, object]) -> tuple[object, ...]:
    return (
        issue.get("category"),
        _object_ref(issue.get("a_raw") or issue.get("a")),
        _object_ref(issue.get("b_raw") or issue.get("b")),
        _object_ref(issue.get("object_raw") or issue.get("object")),
        issue.get("step"),
        issue.get("event"),
    )


def _object_ref(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("path") or value.get("text") or value.get("class") or "")
    return str(value or "")


def _owner(value: Mapping[str, object]) -> str:
    path = str(value.get("path") or "")
    parts = path.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 else path


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
