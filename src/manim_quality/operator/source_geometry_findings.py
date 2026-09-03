"""Static display-space risks derived from explicit coordinate helpers."""

from __future__ import annotations

import ast
import math
import re

PERPENDICULAR = re.compile(r"([A-Z]{2})\s*\\perp\s*([A-Z]{2})")


def screen_geometry_findings(
    tree: ast.Module,
    solution: ast.ClassDef,
) -> list[dict[str, object]]:
    units = _axis_units(tree, solution)
    if units is None:
        return []
    slopes = _line_slopes(solution)
    rows = []
    for first, second in _perpendicular_pairs(solution):
        left, right = slopes.get(first), slopes.get(second)
        if left is None or right is None or abs(left * right + 1.0) > 1e-6:
            continue
        angle = _screen_angle(left, right, *units)
        deviation = abs(90.0 - angle)
        if deviation <= 2.0:
            continue
        rows.append({
            "kind": "anisotropic_perpendicularity",
            "evidence": f"{first} ⟂ {second}; display angle {angle:.2f}°",
            "logical_slopes": [left, right],
            "display_units": [round(units[0], 4), round(units[1], 4)],
            "display_angle_degrees": round(angle, 2),
            "deviation_degrees": round(deviation, 2),
            "invariant": (
                "A claimed perpendicular relation must remain perpendicular "
                "after the coordinate system is mapped into display space."
            ),
        })
    return rows


def _axis_units(tree: ast.Module, solution: ast.ClassDef):
    boxes = _global_config_boxes(tree)
    if boxes is None:
        return None
    for call in (node for node in ast.walk(solution) if isinstance(node, ast.Call)):
        if _call_name(call) != "make_axes_manual":
            continue
        x_range = _keyword_range(call, "x_range")
        y_range = _keyword_range(call, "y_range")
        if x_range is None or y_range is None:
            continue
        data_width = abs(x_range[1] - x_range[0])
        data_height = abs(y_range[1] - y_range[0])
        if data_width > 0 and data_height > 0:
            return (
                abs(boxes[0][1] - boxes[0][0]) / data_width,
                abs(boxes[1][1] - boxes[1][0]) / data_height,
            )
    return None


def _global_config_boxes(tree: ast.Module):
    config = next((node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "GlobalConfig"), None)
    if config is None:
        return None
    values = {}
    for node in config.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id not in {"AXIS_BOX_X_RANGE", "AXIS_BOX_Y_RANGE"}:
            continue
        try:
            values[target.id] = tuple(map(float, ast.literal_eval(node.value)))
        except (TypeError, ValueError):
            continue
    if not all(name in values for name in (
        "AXIS_BOX_X_RANGE", "AXIS_BOX_Y_RANGE",
    )):
        return None
    return values["AXIS_BOX_X_RANGE"], values["AXIS_BOX_Y_RANGE"]


def _line_slopes(solution: ast.ClassDef) -> dict[str, float]:
    result = {}
    for node in ast.walk(solution):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if not isinstance(target, ast.Name) or not target.id.startswith("line_"):
            continue
        if (
            not isinstance(value, ast.Call)
            or _call_name(value) != "make_line_by_formula"
        ):
            continue
        slope = _number(value.args[0] if value.args else None)
        if slope is not None:
            result[target.id.removeprefix("line_").upper()] = slope
    return result


def _perpendicular_pairs(solution: ast.ClassDef) -> set[tuple[str, str]]:
    result = set()
    for node in ast.walk(solution):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        result.update(PERPENDICULAR.findall(node.value))
    return result


def _keyword_range(call: ast.Call, name: str):
    value = next((row.value for row in call.keywords if row.arg == name), None)
    try:
        parsed = tuple(map(float, ast.literal_eval(value)))
    except (TypeError, ValueError):
        return None
    return parsed if len(parsed) >= 2 else None


def _number(node: ast.AST | None) -> float | None:
    try:
        return float(ast.literal_eval(node))
    except (TypeError, ValueError):
        return None


def _screen_angle(first: float, second: float, x_unit: float, y_unit: float):
    a = (x_unit, first * y_unit)
    b = (x_unit, second * y_unit)
    dot = a[0] * b[0] + a[1] * b[1]
    denominator = math.hypot(*a) * math.hypot(*b)
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / denominator))))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""
