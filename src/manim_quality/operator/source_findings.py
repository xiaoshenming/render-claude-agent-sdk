"""Deterministic findings derived from Reviewer-visible Python source."""

from __future__ import annotations

import ast


def collect_solution_findings(solution: ast.ClassDef) -> list[dict[str, object]]:
    return [
        *_opaque_point_findings(solution),
        *_transition_findings(solution),
        *_duplicate_reveal_findings(solution),
        *_duplicate_retire_findings(solution),
    ]


def collect_helper_findings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    owner: str,
) -> list[dict[str, object]]:
    params = {item.arg for item in node.args.args if item.arg != "self"}
    defaults = _parameter_defaults(node)
    rows = []
    for call in (item for item in ast.walk(node) if isinstance(item, ast.Call)):
        name = _call_name(call)
        if name == "Indicate" and call.args and _uses_name(call.args[0], params):
            scale_node = next(
                (item.value for item in call.keywords if item.arg == "scale_factor"),
                None,
            )
            scale = _static_value(scale_node, defaults)
            if scale not in (1, 1.0):
                rows.append({
                    "kind": "transient_scale_on_original_geometry",
                    "helper": f"{owner}.{node.name}",
                    "line": call.lineno,
                    "evidence": ast.unparse(call),
                    "invariant": (
                        "Highlights must animate a copy/overlay and must not "
                        "scale a caller-owned geometry object."
                    ),
                })
        if name == "ReplacementTransform" and len(call.args) >= 2:
            rows.append({
                "kind": "replacement_page_transition",
                "helper": f"{owner}.{node.name}",
                "line": call.lineno,
                "evidence": ast.unparse(call),
                "invariant": (
                    "Whole-page replacement requires source and target to share "
                    "one semantic owner and compatible structure."
                ),
            })
        if name == "Succession":
            nested = {
                _call_name(item) for item in ast.walk(call)
                if isinstance(item, ast.Call)
            }
            if "FadeOut" in nested and any(
                isinstance(item, ast.Name) and item.id in params
                for item in ast.walk(call)
            ):
                rows.append({
                    "kind": "sequential_page_retire_then_reveal",
                    "helper": f"{owner}.{node.name}",
                    "line": call.lineno,
                    "evidence": ast.unparse(call),
                    "invariant": (
                        "A page transition must preserve one meaningful owner "
                        "through the handoff and cannot retire the whole old "
                        "page before the first new content begins."
                    ),
                })
    return rows


def _opaque_point_findings(solution: ast.ClassDef) -> list[dict[str, object]]:
    rows = []
    for node in ast.walk(solution):
        if not isinstance(node, ast.Subscript):
            continue
        value = node.value
        if not (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Attribute)
            and value.func.attr == "get_points"
        ):
            continue
        rows.append({
            "kind": "opaque_semantic_point_index",
            "line": node.lineno,
            "evidence": ast.unparse(node),
            "invariant": (
                "Semantic points and labels must bind to named coordinates, "
                "named Mobjects, or named edge endpoints, never get_points indexes."
            ),
        })
    return rows


def _transition_findings(solution: ast.ClassDef) -> list[dict[str, object]]:
    rows = []
    for node in ast.walk(solution):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"play", "play_steps_evenly"}:
            continue
        calls = [item for item in ast.walk(node) if isinstance(item, ast.Call)]
        names = {_call_name(item) for item in calls}
        if "FadeOut" in names and names & {"Write", "FadeIn", "write_step_row"}:
            rows.append({
                "kind": "crossfade_page_ownership",
                "line": node.lineno,
                "evidence": ast.unparse(node)[:1_200],
                "invariant": (
                    "A page handoff must use one approved transition helper; "
                    "old-page cleanup and new-page first reveal cannot overlap ad hoc."
                ),
            })
    return rows


def _duplicate_reveal_findings(solution: ast.ClassDef) -> list[dict[str, object]]:
    visible: dict[str, int] = {}
    rows = []
    for call in _ordered_calls(solution):
        name = _call_name(call)
        target = call.args[0] if call.args else None
        if not isinstance(target, ast.Name):
            continue
        if name == "FadeOut":
            visible.pop(target.id, None)
            continue
        if name not in {"Create", "FadeIn", "Write"}:
            continue
        if target.id in visible:
            rows.append({
                "kind": "duplicate_reveal_without_retire",
                "line": call.lineno,
                "evidence": (
                    f"{target.id}: first line {visible[target.id]}, "
                    f"repeated {ast.unparse(call)}"
                ),
                "invariant": (
                    "A named Mobject cannot be revealed again while its first "
                    "visible ownership interval is still active."
                ),
            })
        else:
            visible[target.id] = call.lineno
    return rows


def _duplicate_retire_findings(solution: ast.ClassDef) -> list[dict[str, object]]:
    retired: dict[str, int] = {}
    rows = []
    for call in _ordered_calls(solution):
        name = _call_name(call)
        target = call.args[0] if call.args else None
        if not isinstance(target, ast.Name):
            continue
        if name in {"Create", "FadeIn", "Write"}:
            retired.pop(target.id, None)
            continue
        if name != "FadeOut":
            continue
        if target.id in retired:
            rows.append({
                "kind": "duplicate_retire_without_reveal",
                "line": call.lineno,
                "evidence": (
                    f"{target.id}: first line {retired[target.id]}, "
                    f"repeated {ast.unparse(call)}"
                ),
                "invariant": (
                    "A retired named Mobject cannot be faded out again unless a "
                    "new visible ownership interval explicitly revealed it."
                ),
            })
        else:
            retired[target.id] = call.lineno
    return rows


def _ordered_calls(node: ast.AST) -> list[ast.Call]:
    return sorted(
        (item for item in ast.walk(node) if isinstance(item, ast.Call)),
        key=lambda item: (item.lineno, item.col_offset),
    )


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _uses_name(node: ast.AST, names: set[str]) -> bool:
    return any(
        isinstance(item, ast.Name) and item.id in names
        for item in ast.walk(node)
    )


def _parameter_defaults(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[str, object]:
    positional = node.args.args
    values = node.args.defaults
    names = positional[len(positional) - len(values):]
    return {
        name.arg: value.value
        for name, value in zip(names, values, strict=True)
        if isinstance(value, ast.Constant)
    }


def _static_value(node: ast.AST | None, defaults: dict[str, object]):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return defaults.get(node.id)
    return None
