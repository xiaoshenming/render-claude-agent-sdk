"""Bind deterministic geometry mismatches to cited repair issues."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping

from ..repair_plan import RepairPlan

_IDENTITY_KEYS = (
    "kind",
    "class_name",
    "line_var",
    "angle_name",
    "arc_var",
    "point",
    "points",
    "point_vars",
    "move_point",
    "leg_labels",
    "hypotenuse_label",
)


def targeted_geometry_results(
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
    plan: RepairPlan,
) -> tuple[tuple[str, bool, str], ...]:
    baseline_items = _mismatches(baseline)
    baseline_counts = Counter(_kind(item) for item in baseline_items)
    candidate_items = _mismatches(candidate)
    candidate_counts = Counter(_kind(item) for item in candidate_items)
    candidate_ids = {_identity(item) for item in candidate_items}
    results: list[tuple[str, bool, str]] = []
    for issue in plan.issues:
        cited = [
            item
            for item in baseline_items
            if _is_cited(item, issue.target_scene_ids, issue.evidence)
        ]
        if not cited:
            continue
        remaining = [item for item in cited if _identity(item) in candidate_ids]
        kinds = {_kind(item) for item in cited}
        count_decreased = all(
            candidate_counts[kind] < baseline_counts[kind] for kind in kinds
        )
        resolved = not remaining and count_decreased
        detail = (
            "cited deterministic mismatch removed"
            if resolved
            else "cited deterministic mismatch remains"
        )
        results.append((issue.issue_id, resolved, detail))
    return tuple(results)


def _mismatches(facts: Mapping[str, object]) -> list[Mapping[str, object]]:
    values: list[Mapping[str, object]] = []
    for key, items in facts.items():
        if not key.endswith("_mismatches") or not isinstance(items, list):
            continue
        values.extend(item for item in items if isinstance(item, Mapping))
    return values


def _is_cited(item, target_scenes, citations) -> bool:
    source_line = item.get("source_line")
    class_name = item.get("class_name")
    if type(source_line) is not int:
        return False
    return any(
        citation.artifact.value == "candidate_code"
        and citation.line_start is not None
        and citation.line_end is not None
        and citation.line_start <= source_line <= citation.line_end
        and (class_name is None or class_name in target_scenes)
        for citation in citations
    )


def _identity(item: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    return tuple((key, repr(item[key])) for key in _IDENTITY_KEYS if key in item)


def _kind(item: Mapping[str, object]) -> str:
    return str(item.get("kind") or "unknown")
