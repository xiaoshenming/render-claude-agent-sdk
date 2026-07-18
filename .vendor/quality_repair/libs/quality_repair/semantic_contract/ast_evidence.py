"""Legacy AST evidence extractor for source-level geometry contracts."""

from __future__ import annotations

import ast
from dataclasses import dataclass


Point3D = tuple[float, float, float]


@dataclass(frozen=True)
class LineSegment:
    endpoints: tuple[Point3D, Point3D]
    line_no: int


@dataclass
class PointEvidence:
    points: dict[str, Point3D]
    order: list[str]
    lines_by_name: dict[str, int]
    line_segments: dict[str, LineSegment]

    @classmethod
    def from_source(cls, source: str) -> "PointEvidence":
        tree = ast.parse(source)
        evaluator = PointExpressionEvaluator()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                evaluator.handle_assign(node)
        return cls(
            points=evaluator.points,
            order=evaluator.order,
            lines_by_name=evaluator.lines_by_name,
            line_segments=evaluator.line_segments,
        )

    def resolve_point(self, name: str) -> str | None:
        normalized = name.replace("'", "_prime")
        candidates = [
            normalized,
            f"dot_{normalized}",
            f"pt_{normalized}",
            f"{normalized}_rand",
            f"{normalized}_temp",
            f"{normalized}_scaled",
        ]
        if normalized.endswith("_prime"):
            stem = normalized.removesuffix("_prime")
            candidates.extend(
                [
                    f"dot_{stem}_prime",
                    f"pt_{stem}_prime",
                    normalized.replace("_prime", "p"),
                    normalized.replace("_prime", "p_scaled"),
                    f"dot_{normalized.replace('_prime', 'p')}",
                    f"pt_{normalized.replace('_prime', 'p')}",
                ]
            )
        for candidate in candidates:
            if candidate in self.points:
                return candidate
        prefix = normalized + "_"
        for candidate in reversed(self.order):
            if candidate.startswith(prefix) and candidate in self.points:
                return candidate
        return None


class PointExpressionEvaluator:
    def __init__(self) -> None:
        self.points: dict[str, Point3D] = {}
        self.lines: dict[str, tuple[str, str]] = {}
        self.line_segments: dict[str, LineSegment] = {}
        self.order: list[str] = []
        self.lines_by_name: dict[str, int] = {}

    def handle_assign(self, node: ast.Assign) -> None:
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not names:
            return
        line = self._line_value(node.value)
        if line:
            for name in names:
                self.lines[name] = line
            return
        segment = self._line_segment_value(node.value)
        if segment:
            for name in names:
                self.line_segments[name] = LineSegment(segment, node.lineno)
                self.lines_by_name[name] = node.lineno
            return
        point = self._point_value(node.value)
        if point is None:
            return
        for name in names:
            self.points[name] = point
            self.order.append(name)
            self.lines_by_name[name] = node.lineno

    def _line_value(self, node: ast.AST) -> tuple[str, str] | None:
        if isinstance(node, ast.Call) and call_name(node.func) == "Line" and len(node.args) >= 2:
            left = node.args[0].id if isinstance(node.args[0], ast.Name) else None
            right = node.args[1].id if isinstance(node.args[1], ast.Name) else None
            if left in self.points and right in self.points:
                return (left, right)
        return None

    def _point_value(self, node: ast.AST | None) -> Point3D | None:
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return self.points.get(node.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            point = self._point_from_call(node)
            if point is not None:
                return point
        if isinstance(node, ast.BinOp):
            point = self._point_from_binop(node)
            if point is not None:
                return point
        if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) >= 2:
            return self._point_from_sequence(node)
        return None

    def _point_from_call(self, node: ast.Call) -> Point3D | None:
        if node.func.attr == "array" and node.args:
            return self._point_value(node.args[0])
        if node.func.attr == "make_point_by_coord":
            if len(node.args) < 2:
                return None
            x_value = number_node(node.args[0])
            y_value = number_node(node.args[1])
            if x_value is None or y_value is None:
                return None
            return (float(x_value), float(y_value), 0.0)
        if isinstance(node.func.value, ast.Name) and node.func.attr in {"get_start", "get_end"}:
            line = self.lines.get(node.func.value.id)
            if line:
                return self.points.get(line[0 if node.func.attr == "get_start" else 1])
        return None

    def _point_from_binop(self, node: ast.BinOp) -> Point3D | None:
        left = self._point_value(node.left)
        right = self._point_value(node.right)
        scalar_left = number_node(node.left)
        scalar_right = number_node(node.right)
        if isinstance(node.op, ast.Add) and left is not None and right is not None:
            return tuple(a + b for a, b in zip(left, right, strict=True))  # type: ignore[return-value]
        if isinstance(node.op, ast.Sub) and left is not None and right is not None:
            return tuple(a - b for a, b in zip(left, right, strict=True))  # type: ignore[return-value]
        if isinstance(node.op, ast.Mult):
            if left is not None and scalar_right is not None:
                return tuple(a * scalar_right for a in left)  # type: ignore[return-value]
            if right is not None and scalar_left is not None:
                return tuple(a * scalar_left for a in right)  # type: ignore[return-value]
        if isinstance(node.op, ast.Div) and left is not None and scalar_right not in (None, 0):
            return tuple(a / scalar_right for a in left)  # type: ignore[return-value]
        return None

    def _point_from_sequence(self, node: ast.List | ast.Tuple) -> Point3D | None:
        values = [number_node(item) for item in node.elts[:3]]
        if values[0] is None or values[1] is None:
            return None
        z_value = 0.0 if len(values) < 3 or values[2] is None else values[2]
        return (float(values[0]), float(values[1]), float(z_value))

    def _line_segment_value(self, node: ast.AST | None) -> tuple[Point3D, Point3D] | None:
        if not isinstance(node, ast.Call) or call_name(node.func) != "make_line_by_formula":
            return None
        if len(node.args) < 2:
            return None
        slope = number_node(node.args[0])
        intercept = number_node(node.args[1])
        x_range = x_range_from_call(node)
        if slope is None or intercept is None or x_range is None:
            return None
        x1, x2 = x_range
        return ((x1, slope * x1 + intercept, 0.0), (x2, slope * x2 + intercept, 0.0))


def call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def number_node(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = number_node(node.operand)
        return -value if value is not None else None
    if isinstance(node, ast.BinOp):
        left = number_node(node.left)
        right = number_node(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return None if right == 0 else left / right
    return None


def x_range_from_call(node: ast.Call) -> tuple[float, float] | None:
    for keyword in node.keywords:
        if keyword.arg != "x_range":
            continue
        value = keyword.value
        if isinstance(value, (ast.List, ast.Tuple)) and len(value.elts) >= 2:
            left = number_node(value.elts[0])
            right = number_node(value.elts[1])
            if left is not None and right is not None:
                return (float(left), float(right))
    return None
