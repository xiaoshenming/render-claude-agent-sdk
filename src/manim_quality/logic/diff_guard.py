"""AST scope guard for Agent-authored logic repair candidates."""

from __future__ import annotations

import ast
import copy
import difflib
from dataclasses import dataclass

from manim_quality.revisions.fingerprint import code_hash, sha256_text

from .repair_plan import RepairPlan


@dataclass(frozen=True, slots=True)
class DiffGuardResult:
    passed: bool
    changed_scene_ids: tuple[str, ...]
    violations: tuple[str, ...]
    patch_hash: str


def evaluate_logic_diff(before: str, after: str, plan: RepairPlan) -> DiffGuardResult:
    if not isinstance(plan, RepairPlan):
        raise TypeError("plan must be RepairPlan")
    patch_hash = sha256_text(_diff(before, after))
    violations: list[str] = []
    if code_hash(before) != plan.source_code_hash:
        violations.append("source code hash does not match repair plan")
    if before == after:
        violations.append("patch made no changes")
    try:
        before_tree = ast.parse(before)
        after_tree = ast.parse(after)
        compile(after, "candidate.py", "exec")
    except SyntaxError as error:
        violations.append(f"patched candidate is not valid Python: {error.msg}")
        return DiffGuardResult(False, (), tuple(violations), patch_hash)
    changed, scope_errors = _changed_scenes(before_tree, after_tree, plan)
    violations.extend(scope_errors)
    if _masked_dump(before_tree, plan) != _masked_dump(after_tree, plan):
        violations.append("changes outside declared Scenes or to a class header")
    if before != after and not changed and not violations:
        violations.append("patch has no declared Scene semantic change")
    return DiffGuardResult(not violations, changed, tuple(violations), patch_hash)


def _changed_scenes(
    before: ast.Module, after: ast.Module, plan: RepairPlan
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    before_classes = _classes(before)
    after_classes = _classes(after)
    changed: list[str] = []
    violations: list[str] = []
    names = set(before_classes) | set(after_classes)
    for name in sorted(names):
        old, new = before_classes.get(name), after_classes.get(name)
        if _dump(old) == _dump(new):
            continue
        if name not in plan.target_scene_ids:
            violations.append(f"undeclared Scene changed: {name}")
            continue
        if old is None or new is None or _header_dump(old) != _header_dump(new):
            violations.append(f"declared Scene class header changed: {name}")
            continue
        changed.append(name)
    ordered = tuple(name for name in plan.target_scene_ids if name in changed)
    return ordered, tuple(violations)


def _masked_dump(tree: ast.Module, plan: RepairPlan) -> str:
    masked = copy.deepcopy(tree)
    for node in masked.body:
        if isinstance(node, ast.ClassDef) and node.name in plan.target_scene_ids:
            node.body = [ast.Pass()]
    return ast.dump(masked, include_attributes=False)


def _classes(tree: ast.Module) -> dict[str, ast.ClassDef]:
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def _header_dump(node: ast.ClassDef) -> str:
    header = copy.deepcopy(node)
    header.body = [ast.Pass()]
    return ast.dump(header, include_attributes=False)


def _dump(node: ast.AST | None) -> str:
    return "" if node is None else ast.dump(node, include_attributes=False)


def _diff(before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile="before.py",
            tofile="after.py",
        )
    )
