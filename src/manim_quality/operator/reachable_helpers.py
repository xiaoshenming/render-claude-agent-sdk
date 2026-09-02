"""Bounded AST context for helper-aware code-only Reviewers."""

from __future__ import annotations

import ast
import heapq
from collections import deque

from .source_findings import collect_helper_findings, collect_solution_findings

MAX_HELPERS = 56
MAX_HELPER_CHARS = 52_000


def reviewer_source_context(source: str) -> dict[str, object]:
    tree = ast.parse(source)
    classes = {
        node.name: node for node in tree.body if isinstance(node, ast.ClassDef)
    }
    solution = classes.get("Solution")
    if solution is None:
        return {"reachable_helpers": [], "source_findings": []}
    lines = source.splitlines()
    owners = _owner_order(solution, classes)
    methods = _methods_by_owner(owners, classes)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    aliases = _function_aliases(tree)
    helpers, helper_nodes = _collect_helpers(
        solution, owners, methods, functions, aliases, lines)
    findings = [
        *collect_solution_findings(solution),
        *(finding for owner, node in helper_nodes
          for finding in collect_helper_findings(node, owner)),
    ]
    finding_helpers = {
        str(row.get("helper") or "").rsplit(".", 1)[-1]
        for row in findings if row.get("helper")
    }
    selected = [
        row for row in helpers
        if _review_relevant(row["name"]) or row["name"] in finding_helpers
    ]
    return {"reachable_helpers": selected, "source_findings": findings}


def _collect_helpers(solution, owners, methods, functions, aliases, lines):
    sequence = 0
    queue = []
    for name in _self_calls(solution):
        heapq.heappush(queue, (_helper_priority(name), sequence, name))
        sequence += 1
    observed: set[str] = set()
    helpers = []
    helper_nodes = []
    total_chars = 0
    while queue and len(helpers) < MAX_HELPERS:
        _, _, name = heapq.heappop(queue)
        if name in observed:
            continue
        observed.add(name)
        value = _resolve(name, owners, methods, functions, aliases)
        if value is None:
            continue
        owner, node = value
        text = "\n".join(lines[node.lineno - 1:node.end_lineno])
        if total_chars + len(text) > MAX_HELPER_CHARS:
            break
        total_chars += len(text)
        helpers.append({
            "name": name, "owner": owner, "start_line": node.lineno,
            "end_line": node.end_lineno, "source": text,
        })
        helper_nodes.append((owner, node))
        dependencies = (
            _self_calls(node) | _module_calls(node, set(functions) | set(aliases))
        ) - observed
        for dependency in dependencies:
            heapq.heappush(queue, (_helper_priority(dependency), sequence, dependency))
            sequence += 1
    return helpers, helper_nodes


def _owner_order(solution: ast.ClassDef, classes: dict[str, ast.ClassDef]) -> list[str]:
    result = []
    queue = deque(
        base.id for base in solution.bases if isinstance(base, ast.Name)
    )
    while queue:
        name = queue.popleft()
        if name in result:
            continue
        result.append(name)
        value = classes.get(name)
        if value is not None:
            queue.extend(
                base.id for base in value.bases if isinstance(base, ast.Name)
            )
    return result


def _methods_by_owner(owners, classes) -> dict[str, dict[str, ast.FunctionDef]]:
    return {
        owner: {
            node.name: node
            for node in classes[owner].body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for owner in owners if owner in classes
    }


def _resolve(name, owners, methods, functions, aliases):
    value = next(
        ((owner, methods[owner][name]) for owner in owners
         if name in methods.get(owner, {})),
        None,
    )
    target = aliases.get(name, name)
    return value or (("module", functions[target]) if target in functions else None)


def _self_calls(node: ast.AST) -> set[str]:
    return {
        call.func.attr
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "self"
    }


def _module_calls(node: ast.AST, names: set[str]) -> set[str]:
    return {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id in names
    }


def _function_aliases(tree: ast.Module) -> dict[str, str]:
    result = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Name):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                result[target.id] = node.value.id
    return result


def _helper_priority(name: str) -> int:
    return 0 if _review_relevant(name) else 1


def _review_relevant(name: str) -> bool:
    markers = (
        "transition", "switch", "change_page", "retire", "introduce",
        "play_steps", "highlight", "reemphasize", "indicate", "angle_mark",
        "right_mark", "fit_geometry", "fit_left", "anchor",
    )
    return any(marker in name.lower() for marker in markers)
