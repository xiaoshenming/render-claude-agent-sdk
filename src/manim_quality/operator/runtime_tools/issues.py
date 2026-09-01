"""Convert raw probe evidence into bounded Agent-facing layout issues."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from .layout_policy import LAYOUT_POLICY_VERSION, evaluate_downgrade


def compact_layout_report(
    payload: Mapping[str, object],
    *,
    max_issues: int = 20,
    geometry_sidecar: Mapping[str, object] | None = None,
) -> dict[str, object]:
    raw = _raw_issues(payload)
    decisions = [evaluate_downgrade(item, geometry_sidecar) for item in raw]
    blocking_count = sum(1 for policy in decisions if policy is None)
    candidates = _compact_candidates(payload.get("agent_bbox_candidates"))
    issue_limit = min(max_issues, 8) if any(candidates.values()) else max_issues
    issues = [
        _compact_issue(item, policy)
        for item, policy in zip(raw[:issue_limit], decisions, strict=False)
    ]
    probe_summary = payload.get("raw")
    if not isinstance(probe_summary, Mapping):
        probe_summary = payload
    return {
        "blocking_count": blocking_count,
        "downgraded_count": len(raw) - blocking_count,
        "layout_policy_version": LAYOUT_POLICY_VERSION,
        "returned_issue_count": len(issues),
        "truncated": len(raw) > len(issues),
        "issues": issues,
        "agent_bbox_candidates": candidates,
        "probe_summary": {
            "snapshot_count": probe_summary.get("snapshot_count"),
            "estimated_duration": probe_summary.get("estimated_duration"),
            "raw_issue_count": len(raw),
        },
    }


def _compact_candidates(value: object) -> dict[str, list[dict[str, object]]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        name: [_compact_candidate(row) for row in rows[:20]
               if isinstance(row, Mapping)]
        for name in (
            "semantic_row_overlaps", "raw_overlaps", "raw_bounds_violations",
        )
        if isinstance((rows := value.get(name)), list)
    }


def _compact_candidate(row: Mapping[str, object]) -> dict[str, object]:
    objects = {
        name: _object_ref(row.get(name))
        for name in ("a", "b", "object")
        if _object_ref(row.get(name)) is not None
    }
    return {
        "category": row.get("category"),
        "step": row.get("step"),
        "event": row.get("event"),
        "time_window": row.get("time_window"),
        "ratio_of_smaller": row.get("ratio_of_smaller"),
        "x_overlap": row.get("x_overlap"),
        "y_overlap": row.get("y_overlap"),
        "overflow_x": row.get("overflow_x"),
        "overflow_y": row.get("overflow_y"),
        **objects,
    }


def _raw_issues(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    values = list(payload.get("issues") or [])
    return [item for item in values if isinstance(item, Mapping)]


def _compact_issue(
    issue: Mapping[str, object],
    policy: Mapping[str, object] | None = None,
) -> dict[str, object]:
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
        "severity": "warning" if policy else "blocking",
        **({"policy": dict(policy)} if policy else {}),
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
        for key in ("path", "class", "kind", "text", "role")
        if value.get(key) not in (None, "")
    } | ({"bbox": bbox} if isinstance(bbox, Mapping) else {})


def _acceptance(category: str) -> str:
    if category == "frame_bounds_overflow":
        return "Object remains inside the configured frame on every probe snapshot."
    return "The reported pair no longer has a blocking collision on any snapshot."
