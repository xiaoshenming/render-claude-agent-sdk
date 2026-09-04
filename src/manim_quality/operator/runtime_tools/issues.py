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
    evidence_only = payload.get("evidence_only") is True
    decisions = [evaluate_downgrade(item, geometry_sidecar) for item in raw]
    blocking_count = 0 if evidence_only else sum(1 for policy in decisions if policy is None)
    issues = [
        _compact_issue(item, policy, evidence_only=evidence_only)
        for item, policy in zip(raw[:max_issues], decisions, strict=False)
    ]
    probe_summary = payload.get("raw")
    if not isinstance(probe_summary, Mapping):
        probe_summary = payload
    result = {
        "evidence_only": evidence_only,
        "evidence_version": payload.get("evidence_version"),
        "candidate_count": len(raw),
        "blocking_count": blocking_count,
        "downgraded_count": sum(policy is not None for policy in decisions),
        "layout_policy_version": LAYOUT_POLICY_VERSION,
        "returned_issue_count": len(issues),
        "truncated": len(raw) > len(issues),
        "issues": issues,
        "probe_summary": {
            "capture_mode": probe_summary.get("capture_mode"),
            "snapshot_count": probe_summary.get("snapshot_count"),
            "estimated_duration": probe_summary.get("estimated_duration"),
            "raw_issue_count": probe_summary.get("raw_issue_count", len(raw)),
            "warning_count": probe_summary.get("warning_count", 0),
            "legacy_errors_reclassified": probe_summary.get(
                "legacy_errors_reclassified", False),
        },
    }
    # Preserve complete facts in the detector artifact, keep one bounded tool payload.
    while issues and len(json.dumps(result, ensure_ascii=False)) > 24_000:
        issues.pop()
        result["returned_issue_count"] = len(issues)
        result["truncated"] = True
    return result


def _raw_issues(payload: Mapping[str, object]) -> list[Mapping[str, object]]:
    values = list(payload.get("issues") or [])
    return [item for item in values if isinstance(item, Mapping)]


def _compact_issue(
    issue: Mapping[str, object],
    policy: Mapping[str, object] | None = None,
    *, evidence_only: bool = False,
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
        "severity": "candidate" if evidence_only else "warning" if policy else "blocking",
        **({"policy": dict(policy)} if policy else {}),
        "objects": objects,
        "phase": {
            "step": issue.get("step"),
            "event": issue.get("event"),
            "time_window": issue.get("time_window"),
            "occurrences": issue.get("occurrences", 1),
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
        "acceptance_criteria": (
            "Judge readability and intended contact using source and these geometric facts. "
            "A candidate is not a confirmed defect; no candidates does not rule out drift."
            if evidence_only else _acceptance(category)
        ),
    }


def _object_ref(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    bbox = value.get("bbox")
    result = {
        key: value.get(key)
        for key in ("path", "class", "kind", "text")
        if value.get(key) not in (None, "")
    } | ({"bbox": bbox} if isinstance(bbox, Mapping) else {})
    if len(str(result.get("text") or "")) > 240:
        result["text"] = str(result["text"])[:240]
        result["text_truncated"] = True
    return result


def _acceptance(category: str) -> str:
    if category == "frame_bounds_overflow":
        return "Object remains inside the configured frame on every probe snapshot."
    return "The reported pair no longer has a blocking collision on any snapshot."
