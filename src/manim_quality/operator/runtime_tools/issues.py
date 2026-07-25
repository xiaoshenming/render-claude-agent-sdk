"""Convert raw probe evidence into bounded Agent-facing layout issues."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping


def compact_layout_report(
    payload: Mapping[str, object],
    *,
    max_issues: int = 20,
) -> dict[str, object]:
    raw = _raw_issues(payload)
    issues = [_compact_issue(item) for item in raw[:max_issues]]
    probe_summary = payload.get("raw")
    if not isinstance(probe_summary, Mapping):
        probe_summary = payload
    return {
        "blocking_count": len(raw),
        "returned_issue_count": len(issues),
        "truncated": len(raw) > len(issues),
        "issues": issues,
        "probe_summary": {
            "snapshot_count": probe_summary.get("snapshot_count"),
            "estimated_duration": probe_summary.get("estimated_duration"),
            "raw_issue_count": len(raw),
        },
    }


def _raw_issues(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    values = list(payload.get("issues") or [])
    return [item for item in values if isinstance(item, Mapping)]


def _compact_issue(issue: Mapping[str, object]) -> dict[str, object]:
    category = str(issue.get("category") or "unknown")
    objects = [
        _object_ref(issue.get(f"{key}_raw") or issue.get(key))
        for key in ("a", "b", "object")
    ]
    objects = [item for item in objects if item is not None]
    identity = json.dumps(
        [category, objects, issue.get("step"), issue.get("event")],
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "issue_id": "layout-" + hashlib.sha256(identity.encode()).hexdigest()[:12],
        "category": category,
        "objects": objects,
        "phase": {
            "step": issue.get("step"),
            "event": issue.get("event"),
            "time_window": issue.get("time_window"),
        },
        "geometry": {
            key: issue.get(key)
            for key in (
                "ratio_of_smaller",
                "x_overlap",
                "y_overlap",
                "overflow_x",
                "overflow_y",
                "sides",
            )
            if key in issue
        },
        "acceptance_criteria": _acceptance(category),
    }


def _object_ref(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    bbox = value.get("bbox")
    return {
        key: value.get(key)
        for key in ("path", "class", "kind", "text")
        if value.get(key) not in (None, "")
    } | ({"bbox": bbox} if isinstance(bbox, Mapping) else {})


def _acceptance(category: str) -> str:
    if category == "frame_bounds_overflow":
        return "Object remains inside the configured frame on every probe snapshot."
    return "The reported pair no longer has a blocking collision on any snapshot."
