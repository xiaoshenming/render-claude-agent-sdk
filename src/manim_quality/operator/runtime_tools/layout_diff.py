"""Compact before/after layout evidence and shared-root clusters."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence


def issue_key(issue: Mapping[str, object]) -> str:
    value = {
        "category": issue.get("category"),
        "objects": issue.get("objects"),
        "phase": issue.get("phase"),
    }
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compare_layout_reports(
    baseline: Mapping[str, object],
    current: Mapping[str, object],
) -> dict[str, object]:
    before_issues = _issues(baseline)
    after_issues = _issues(current)
    before_keys = {issue_key(item) for item in before_issues}
    after_keys = {issue_key(item) for item in after_issues}
    return {
        "before": _blocking(baseline),
        "after": _blocking(current),
        "resolved_count": len(before_keys - after_keys),
        "persistent_count": len(before_keys & after_keys),
        "introduced_count": len(after_keys - before_keys),
        "shared_roots": shared_root_clusters(after_issues),
    }


def shared_root_clusters(
    issues: Sequence[Mapping[str, object]],
    *,
    limit: int = 8,
) -> list[dict[str, object]]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[Mapping[str, object]]] = {}
    for issue in issues:
        roots = _roots(issue)
        for root in roots:
            counts[root] += 1
            examples.setdefault(root, []).append(issue)
    ranked = sorted(counts, key=lambda root: (-counts[root], root))[:limit]
    return [
        {
            "root": root,
            "affected_issue_count": counts[root],
            "representative_issue_ids": [
                str(item.get("issue_id")) for item in examples[root][:3]
            ],
        }
        for root in ranked
        if counts[root] > 1
    ]


def _issues(report: Mapping[str, object]) -> list[Mapping[str, object]]:
    raw = report.get("issues")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [item for item in raw if isinstance(item, Mapping)]


def _blocking(report: Mapping[str, object]) -> int:
    value = report.get("blocking_count")
    return value if type(value) is int and value >= 0 else len(_issues(report))


def _roots(issue: Mapping[str, object]) -> set[str]:
    roots: set[str] = set()
    objects = issue.get("objects")
    if isinstance(objects, Sequence) and not isinstance(objects, (str, bytes)):
        for item in objects:
            if not isinstance(item, Mapping):
                continue
            path = item.get("path")
            if isinstance(path, str) and path:
                roots.add(f"object:{path}")
    phase = issue.get("phase")
    if isinstance(phase, Mapping):
        step = phase.get("step")
        event = phase.get("event")
        if step is not None or event is not None:
            roots.add(f"phase:{step}:{event}")
    category = issue.get("category")
    if not roots and isinstance(category, str):
        roots.add(f"category:{category}")
    return roots
