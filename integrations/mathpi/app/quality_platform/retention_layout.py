"""Allowlisted layout evidence retained in quality events."""

from __future__ import annotations

from typing import Any, Callable, Mapping


def layout_summary(
    value: Any,
    *,
    text: Callable[[Any, int], str],
    sanitize: Callable[[Any, int], str],
    number: Callable[[Any], int | None],
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    counts = value.get("category_counts")
    impacts = value.get("impact_counts")
    examples = value.get("examples")
    return {
        "policy_version": text(value.get("policy_version"), 80),
        "raw_count": number(value.get("raw_count")),
        "actionable_count": number(value.get("actionable_count")),
        "record_only_count": number(value.get("record_only_count")),
        "category_counts": dict(counts) if isinstance(counts, Mapping) else {},
        "impact_counts": dict(impacts) if isinstance(impacts, Mapping) else {},
        "examples": [
            _layout_issue(item, sanitize=sanitize, number=number)
            for item in (examples if isinstance(examples, list) else [])[:20]
            if isinstance(item, Mapping)
        ],
    }


def _layout_issue(
    value: Mapping[str, Any],
    *,
    sanitize: Callable[[Any, int], str],
    number: Callable[[Any], int | None],
) -> dict[str, Any]:
    objects = value.get("objects")
    return {
        "category": sanitize(value.get("category"), 80),
        "impact": sanitize(value.get("impact"), 40),
        "reason": sanitize(value.get("reason"), 160),
        "scene": sanitize(value.get("scene"), 160),
        "event": sanitize(value.get("event"), 80),
        "time_window": dict(value.get("time_window") or {}),
        "occurrence_count": number(value.get("occurrence_count")),
        "observed_duration": value.get("observed_duration"),
        "ratio_of_smaller": value.get("ratio_of_smaller"),
        "objects": [
            {
                "class": sanitize(item.get("class"), 100),
                "kind": sanitize(item.get("kind"), 40),
                "text": sanitize(item.get("text"), 300),
                "bbox": dict(item.get("bbox") or {}),
            }
            for item in (objects if isinstance(objects, list) else [])[:2]
            if isinstance(item, Mapping)
        ],
    }
