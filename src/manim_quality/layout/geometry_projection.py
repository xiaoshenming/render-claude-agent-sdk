"""Conservative translation normalization for unframed Euclidean diagrams."""

from __future__ import annotations

import ast
from collections.abc import Iterable

_FRAMES = frozenset({"Axes", "ComplexPlane", "NumberLine", "NumberPlane", "ThreeDAxes"})
_GEOMETRY_CALLS = frozenset(
    {
        "ArcBetweenPoints",
        "Arrow",
        "DashedLine",
        "Dot",
        "Line",
        "Polygon",
        "RightAngle",
        "Vector",
    }
)
_DIRECTIONS = {
    "ORIGIN": (0.0, 0.0, 0.0),
    "RIGHT": (1.0, 0.0, 0.0),
    "LEFT": (-1.0, 0.0, 0.0),
    "UP": (0.0, 1.0, 0.0),
    "DOWN": (0.0, -1.0, 0.0),
    "OUT": (0.0, 0.0, 1.0),
    "IN": (0.0, 0.0, -1.0),
}


def normalize_unframed_translations(tree: ast.AST) -> ast.AST:
    """Ignore a common translation only when coordinate uses stay geometric."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _normalize_function(node)
    return tree


def _normalize_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
    if _contains_coordinate_frame(node):
        return
    assignments = _vector_assignments(node.body)
    if len(assignments) < 2:
        return
    names = {name for _, name, _ in assignments}
    if not _uses_preserve_translation(node, names):
        return
    anchor = assignments[0][2]
    for assignment, _, value in assignments:
        relative = tuple(
            round(item - base, 12) for item, base in zip(value, anchor, strict=True)
        )
        assignment.value = ast.Tuple(
            elts=[ast.Constant(value=item) for item in relative],
            ctx=ast.Load(),
        )


def _contains_coordinate_frame(node: ast.AST) -> bool:
    return any(
        isinstance(item, ast.Call) and _call_name(item) in _FRAMES
        for item in ast.walk(node)
    )


def _vector_assignments(
    statements: Iterable[ast.stmt],
) -> list[tuple[ast.Assign, str, tuple[float, float, float]]]:
    found = []
    for statement in statements:
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        target = statement.targets[0]
        value = _vector(statement.value)
        if isinstance(target, ast.Name) and value is not None:
            found.append((statement, target.id, value))
    return found


def _uses_preserve_translation(node: ast.AST, names: set[str]) -> bool:
    allowed: set[ast.Name] = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Call) and _call_name(item) in _GEOMETRY_CALLS:
            allowed.update(_point_loads(item, names))
        elif isinstance(item, ast.Assign):
            weight = _translation_weight(item.value, names)
            if weight is not None and weight in {0.0, 1.0}:
                allowed.update(_point_loads(item.value, names))
    for item in ast.walk(node):
        if not isinstance(item, ast.Name) or not isinstance(item.ctx, ast.Load):
            continue
        if item.id in names and item not in allowed:
            return False
    return True


def _point_loads(node: ast.AST, names: set[str]) -> set[ast.Name]:
    return {
        item
        for item in ast.walk(node)
        if isinstance(item, ast.Name)
        and isinstance(item.ctx, ast.Load)
        and item.id in names
    }


def _translation_weight(node: ast.AST, names: set[str]) -> float | None:
    if isinstance(node, ast.Name):
        return 1.0 if node.id in names else 0.0
    if isinstance(node, ast.Constant):
        return 0.0
    if isinstance(node, ast.UnaryOp):
        weight = _translation_weight(node.operand, names)
        if weight is None:
            return None
        return -weight if isinstance(node.op, ast.USub) else weight
    if isinstance(node, ast.BinOp):
        return _binop_weight(node, names)
    if isinstance(node, ast.Call) and _call_name(node) == "norm" and node.args:
        weight = _translation_weight(node.args[0], names)
        return 0.0 if weight == 0.0 else None
    if isinstance(node, (ast.Tuple, ast.List)):
        weights = [_translation_weight(item, names) for item in node.elts]
        return 0.0 if all(item == 0.0 for item in weights) else None
    return None


def _binop_weight(node: ast.BinOp, names: set[str]) -> float | None:
    left = _translation_weight(node.left, names)
    right = _translation_weight(node.right, names)
    if left is None or right is None:
        return None
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    right_scalar = _scalar(node.right)
    left_scalar = _scalar(node.left)
    if isinstance(node.op, ast.Mult):
        if right_scalar is not None:
            return left * right_scalar
        if left_scalar is not None:
            return right * left_scalar
        return 0.0 if left == right == 0.0 else None
    if isinstance(node.op, ast.Div):
        if right_scalar not in {None, 0}:
            return left / right_scalar
        return 0.0 if left == right == 0.0 else None
    return None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _vector(node: ast.AST) -> tuple[float, float, float] | None:
    if isinstance(node, ast.Name):
        return _DIRECTIONS.get(node.id)
    if isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) in {2, 3}:
        values = [_scalar(item) for item in node.elts]
        if any(item is None for item in values):
            return None
        return (
            float(values[0]),
            float(values[1]),
            float(values[2] if len(values) == 3 else 0.0),
        )
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _vector(node.operand)
        return None if value is None else tuple(-item for item in value)
    if not isinstance(node, ast.BinOp):
        return None
    left, right = _vector(node.left), _vector(node.right)
    if (
        isinstance(node.op, (ast.Add, ast.Sub))
        and left is not None
        and right is not None
    ):
        sign = 1 if isinstance(node.op, ast.Add) else -1
        return tuple(a + sign * b for a, b in zip(left, right, strict=True))
    return _scaled_vector(node, left, right)


def _scaled_vector(
    node: ast.BinOp,
    left: tuple[float, float, float] | None,
    right: tuple[float, float, float] | None,
) -> tuple[float, float, float] | None:
    left_scalar, right_scalar = _scalar(node.left), _scalar(node.right)
    if isinstance(node.op, ast.Mult):
        if left is not None and right_scalar is not None:
            return tuple(item * right_scalar for item in left)
        if right is not None and left_scalar is not None:
            return tuple(item * left_scalar for item in right)
    if (
        isinstance(node.op, ast.Div)
        and left is not None
        and right_scalar not in {None, 0}
    ):
        return tuple(item / right_scalar for item in left)
    return None


def _scalar(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _scalar(node.operand)
        return None if value is None else -value
    return None
