"""AST-based Scene targeting and deterministic modification scope checks."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from manim_quality.rendering.impact import analyze_source
from manim_quality.revisions.fingerprint import scene_fingerprints


class ModificationScopeError(ValueError):
    """The requested Scene scope is invalid or the candidate escaped it."""


@dataclass(frozen=True, slots=True)
class SceneRegion:
    scene_id: str
    line_start: int
    line_end: int
    source: str


@dataclass(frozen=True, slots=True)
class ModificationPlan:
    ordered_scene_ids: tuple[str, ...]
    target_scene_ids: tuple[str, ...]
    editable_regions: tuple[SceneRegion, ...]
    context_regions: tuple[SceneRegion, ...]


def plan_modification(
    source: str, target_scene_ids: tuple[str, ...]
) -> ModificationPlan:
    classes = _scene_classes(source)
    ordered = tuple(classes)
    targets = _targets(target_scene_ids, ordered)
    editable = tuple(_region(source, classes[name]) for name in targets)
    context_names = _adjacent_names(ordered, targets)
    context = tuple(_region(source, classes[name]) for name in context_names)
    return ModificationPlan(ordered, targets, editable, context)


def validate_modification(
    before: str, candidate: str, plan: ModificationPlan
) -> tuple[str, ...]:
    if not isinstance(plan, ModificationPlan):
        raise TypeError("plan must be ModificationPlan")
    candidate_plan = plan_modification(candidate, plan.target_scene_ids)
    if candidate_plan.ordered_scene_ids != plan.ordered_scene_ids:
        raise ModificationScopeError("Scene order or membership changed")
    before_impact = analyze_source(before, plan.ordered_scene_ids)
    try:
        candidate_impact = analyze_source(candidate, plan.ordered_scene_ids)
    except (SyntaxError, ValueError) as error:
        raise ModificationScopeError(str(error)) from error
    if before_impact.shared_dependency_hash != candidate_impact.shared_dependency_hash:
        raise ModificationScopeError("shared dependencies changed")
    changed = tuple(
        scene_id
        for scene_id in plan.ordered_scene_ids
        if before_impact.scene_hashes[scene_id]
        != candidate_impact.scene_hashes[scene_id]
    )
    unchanged_targets = set(plan.target_scene_ids).difference(changed)
    if unchanged_targets:
        raise ModificationScopeError(
            "requested Scene unchanged: " + ", ".join(sorted(unchanged_targets))
        )
    escaped = set(changed).difference(plan.target_scene_ids)
    if escaped:
        raise ModificationScopeError(
            "unrequested Scene changed: " + ", ".join(sorted(escaped))
        )
    return changed


def _scene_classes(source: str) -> dict[str, ast.ClassDef]:
    if not isinstance(source, str) or not source.strip():
        raise ModificationScopeError("source must be non-empty Python")
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ModificationScopeError(str(error)) from error
    scene_names = set(scene_fingerprints(source))
    classes = {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in scene_names
    }
    if not classes:
        raise ModificationScopeError("source contains no top-level Scene")
    return classes


def _targets(value: tuple[str, ...], ordered: tuple[str, ...]) -> tuple[str, ...]:
    if not value or len(set(value)) != len(value):
        raise ModificationScopeError("target Scene IDs must be non-empty and unique")
    unknown = set(value).difference(ordered)
    if unknown:
        raise ModificationScopeError("unknown Scene: " + ", ".join(sorted(unknown)))
    requested = set(value)
    return tuple(name for name in ordered if name in requested)


def _adjacent_names(
    ordered: tuple[str, ...], targets: tuple[str, ...]
) -> tuple[str, ...]:
    target_set = set(targets)
    indexes = {ordered.index(name) for name in targets}
    adjacent = {
        ordered[index]
        for target in indexes
        for index in (target - 1, target + 1)
        if 0 <= index < len(ordered) and ordered[index] not in target_set
    }
    return tuple(name for name in ordered if name in adjacent)


def _region(source: str, node: ast.ClassDef) -> SceneRegion:
    lines = source.splitlines()
    end = node.end_lineno or node.lineno
    excerpt = "\n".join(lines[node.lineno - 1 : end])
    return SceneRegion(node.name, node.lineno, end, excerpt)
