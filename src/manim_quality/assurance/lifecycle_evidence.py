"""Deterministic source evidence for semantic-view ownership leaks."""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path


def detached_transition_parts(source_path: Path | None) -> tuple[dict, ...]:
    if source_path is None or not source_path.is_file():
        return ()
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return ()
    construct = _solution_construct(tree)
    if construct is None:
        return ()
    groups = _group_assignments(construct)
    uses = _part_uses(construct)
    transitions = _transitions(construct)
    findings = []
    for call in _calls_named(construct, "adopt_input_visual"):
        root = _name(call.args[0]) if call.args else None
        parts = _parts(call)
        if root is None or root not in transitions or not parts:
            continue
        owned = _owned_names(root, groups)
        for part, object_name in parts.items():
            use_lines = uses.get((root, part), ())
            if object_name in owned or not use_lines:
                continue
            findings.append(
                {
                    "category": "detached_transition_part",
                    "root": root,
                    "part": part,
                    "object_name": object_name,
                    "registration_line": call.lineno,
                    "use_lines": list(use_lines),
                    "transition_line": transitions[root],
                }
            )
    return tuple(sorted(findings, key=_finding_key))


def _solution_construct(tree: ast.AST) -> ast.FunctionDef | None:
    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, ast.ClassDef) or node.name != "Solution":
            continue
        return next(
            (
                item
                for item in node.body
                if isinstance(item, ast.FunctionDef) and item.name == "construct"
            ),
            None,
        )
    return None


def _group_assignments(function: ast.FunctionDef) -> dict[str, tuple[str, ...]]:
    groups = {}
    for node in ast.walk(function):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        target = node.targets[0] if isinstance(node, ast.Assign) else node.target
        value = node.value
        name = _name(target)
        if name is None or not isinstance(value, ast.Call):
            continue
        if _call_name(value) not in {"Group", "VGroup"}:
            continue
        groups[name] = tuple(
            item for item in (_name(argument) for argument in value.args) if item
        )
    return groups


def _part_uses(function: ast.FunctionDef) -> dict[tuple[str, str], tuple[int, ...]]:
    rows: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    for call in _calls_named(function, "get_source_part"):
        if len(call.args) < 2:
            continue
        root = _name(call.args[0])
        part = call.args[1].value if isinstance(call.args[1], ast.Constant) else None
        if root and isinstance(part, str):
            rows[(root, part)].append(call.lineno)
    return {key: tuple(sorted(set(lines))) for key, lines in rows.items()}


def _transitions(function: ast.FunctionDef) -> dict[str, int]:
    rows = {}
    for call in _calls_named(function, "transition_semantic_view"):
        root = _name(call.args[0]) if call.args else None
        if root:
            rows.setdefault(root, call.lineno)
    return rows


def _parts(call: ast.Call) -> dict[str, str]:
    value = next((item.value for item in call.keywords if item.arg == "parts"), None)
    if not isinstance(value, ast.Dict):
        return {}
    rows = {}
    for key, item in zip(value.keys, value.values, strict=True):
        part = key.value if isinstance(key, ast.Constant) else None
        object_name = _name(item)
        if isinstance(part, str) and object_name:
            rows[part] = object_name
    return rows


def _owned_names(root: str, groups: dict[str, tuple[str, ...]]) -> set[str]:
    owned = set()
    pending = list(groups.get(root, ()))
    while pending:
        name = pending.pop()
        if name in owned:
            continue
        owned.add(name)
        pending.extend(groups.get(name, ()))
    return owned


def _calls_named(node: ast.AST, name: str):
    return (
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and _call_name(item) == name
    )


def _call_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _name(node: ast.AST) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _finding_key(value: dict) -> tuple[int, str]:
    return int(value["registration_line"]), str(value["part"])
