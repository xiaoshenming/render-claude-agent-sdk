"""Small AST primitives shared by static geometry indexing."""

from __future__ import annotations

import ast

_NON_MUTATING_METHODS = frozenset({"copy"})


def literal_vector(node: ast.AST) -> list[int | float] | None:
    try:
        value = ast.literal_eval(node)
    except (TypeError, ValueError):
        return None
    if not isinstance(value, (list, tuple)) or len(value) not in {2, 3}:
        return None
    if any(
        isinstance(item, bool) or not isinstance(item, (int, float)) for item in value
    ):
        return None
    return list(value)


def literal_number(node: ast.AST) -> int | float | None:
    try:
        value = ast.literal_eval(node)
    except (TypeError, ValueError):
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def keyword(call: ast.Call, name: str) -> ast.AST | None:
    for item in call.keywords:
        if item.arg == name:
            return item.value
    return None


def assigned_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def dynamically_changed_names(construct: ast.FunctionDef) -> set[str]:
    changed: set[str] = set()
    for node in ast.walk(construct):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method.startswith("get_") or method in _NON_MUTATING_METHODS:
                continue
            name = _root_name(node.func.value)
            if name is not None:
                changed.add(name)
            continue
        if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
        for target in targets:
            if isinstance(target, (ast.Attribute, ast.Subscript)):
                name = _root_name(target)
                if name is not None:
                    changed.add(name)
    return changed


def _root_name(node: ast.AST) -> str | None:
    current = node
    while isinstance(current, (ast.Attribute, ast.Subscript)):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None
