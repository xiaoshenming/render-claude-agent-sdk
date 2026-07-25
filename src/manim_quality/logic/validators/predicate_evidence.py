"""AST-bound evidence for computable acceptance predicates."""

from __future__ import annotations

import ast

from .._scene_evidence import extract_scenes

_DISPLAY_CALLS = frozenset(
    {
        "DecimalNumber",
        "Integer",
        "MarkupText",
        "MathTex",
        "Matrix",
        "Tex",
        "Text",
        "Variable",
    }
)
_FORMULA_CALLS = _DISPLAY_CALLS | frozenset(
    {"FunctionGraph", "ImplicitFunction", "ParametricFunction"}
)
_COORDINATE_CALLS = frozenset(
    {
        "Arrow",
        "Dot",
        "Line",
        "Vector",
        "c2p",
        "coords_to_point",
        "make_point_by_coord",
        "move_to",
    }
)
_DISPLAY_SINKS = frozenset(
    {"add", "add_fixed_in_frame_mobjects", "add_foreground_mobject", "play"}
)


def predicate_has_bound_evidence(
    code: str, *, kind: str, value: str, scene_id: object
) -> bool | None:
    """Return true/false when the predicate maps to a known active call."""
    call_names = _call_names(kind)
    if call_names is None:
        return None
    tree = ast.parse(code)
    targets = _target_nodes(tree, scene_id)
    if targets is None:
        return None
    return any(
        _call_name(call.func) in call_names
        and _contains_value(ast.get_source_segment(code, call) or "", value)
        for target in targets
        for call in _reachable_calls(target)
    )


def _call_names(kind: str) -> frozenset[str] | None:
    if kind in {"expected_answer_present", "text_present"}:
        return _DISPLAY_CALLS
    if kind == "formula_present":
        return _FORMULA_CALLS
    if kind == "coordinate_present":
        return _COORDINATE_CALLS
    return None


def _target_nodes(tree: ast.Module, scene_id: object) -> tuple[ast.AST, ...] | None:
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    if isinstance(scene_id, str) and scene_id.strip():
        target = classes.get(scene_id)
        return (target,) if target is not None else None
    scene_ids = {scene.scene_id for scene in extract_scenes(ast.unparse(tree))}
    return tuple(classes[name] for name in sorted(scene_ids) if name in classes)


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _reachable_calls(target: ast.AST) -> tuple[ast.Call, ...]:
    assignments = _assignments(target)
    pending = [
        arg
        for node in ast.walk(target)
        if isinstance(node, ast.Call) and _call_name(node.func) in _DISPLAY_SINKS
        for arg in (*node.args, *(keyword.value for keyword in node.keywords))
    ]
    visited_names: set[str] = set()
    calls: list[ast.Call] = []
    while pending:
        node = pending.pop()
        calls.extend(item for item in ast.walk(node) if isinstance(item, ast.Call))
        for name in {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}:
            if name in visited_names or name not in assignments:
                continue
            visited_names.add(name)
            pending.append(assignments[name])
    return tuple(calls)


def _assignments(target: ast.AST) -> dict[str, ast.AST]:
    values: dict[str, ast.AST] = {}
    for node in ast.walk(target):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = _assigned_name(node.targets[0])
            if name is not None:
                values[name] = node.value
        elif isinstance(node, ast.AnnAssign):
            name = _assigned_name(node.target)
            if name is not None and node.value is not None:
                values[name] = node.value
    return values


def _assigned_name(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _compact(value: str) -> str:
    return "".join(value.split()).replace('"', "").replace("'", "")


def _contains_value(source: str, value: str) -> bool:
    haystack = _compact(source)
    needle = _compact(value)
    if not needle:
        return False
    start = haystack.find(needle)
    while start >= 0:
        end = start + len(needle)
        left = haystack[start - 1] if start else ""
        right = haystack[end] if end < len(haystack) else ""
        if not _continues_token(left, needle[0]) and not _continues_token(
            needle[-1], right
        ):
            return True
        start = haystack.find(needle, start + 1)
    return False


def _continues_token(left: str, right: str) -> bool:
    if not left or not right:
        return False
    identifiers_continue = (left.isalnum() or left == "_") and (
        right.isalnum() or right == "_"
    )
    return identifiers_continue or (
        (left == "." and right.isdigit()) or (left.isdigit() and right == ".")
    )
