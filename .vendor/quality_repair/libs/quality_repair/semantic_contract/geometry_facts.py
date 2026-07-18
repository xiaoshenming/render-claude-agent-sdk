"""Extract compact geometry facts from Manim candidate code."""

from __future__ import annotations

import ast
import math
from dataclasses import dataclass, field
from typing import Any


Point3 = tuple[float, float, float]


@dataclass(frozen=True)
class LineSegment:
    endpoints: tuple[Point3, Point3]
    line_no: int


@dataclass(frozen=True)
class GeometryFacts:
    points: dict[str, Point3] = field(default_factory=dict)
    scalars: dict[str, float] = field(default_factory=dict)
    lines: dict[str, tuple[str, str]] = field(default_factory=dict)
    line_segments: dict[str, LineSegment] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)
    lines_by_name: dict[str, int] = field(default_factory=dict)

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


def extract_geometry_facts(source: str, *, scene_name: str | None = None) -> GeometryFacts:
    tree = ast.parse(source)
    search_nodes: list[ast.AST] = [tree]
    if scene_name:
        matching = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == scene_name]
        if matching:
            search_nodes = matching
    evaluator = _GeometryEvaluator()
    for root in search_nodes:
        evaluator.visit(root)
    return GeometryFacts(
        points=evaluator.points,
        scalars=evaluator.scalars,
        lines=evaluator.lines,
        line_segments=evaluator.line_segments,
        order=evaluator.order,
        lines_by_name=evaluator.lines_by_name,
    )


class _GeometryEvaluator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.points: dict[str, Point3] = {}
        self.scalars: dict[str, float] = {}
        self.lines: dict[str, tuple[str, str]] = {}
        self.line_segments: dict[str, LineSegment] = {}
        self.order: list[str] = []
        self.lines_by_name: dict[str, int] = {}

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if not names:
            self.generic_visit(node)
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
        if point is not None:
            for name in names:
                self.points[name] = point
                self.order.append(name)
                self.lines_by_name[name] = node.lineno
            return
        scalar = self._number_value(node.value)
        if scalar is not None:
            for name in names:
                self.scalars[name] = scalar
            return
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        if not isinstance(node.target, ast.Name):
            self.generic_visit(node)
            return
        point = self._point_value(node.value)
        if point is not None:
            self.points[node.target.id] = point
            self.order.append(node.target.id)
            self.lines_by_name[node.target.id] = node.lineno
            return
        scalar = self._number_value(node.value)
        if scalar is not None:
            self.scalars[node.target.id] = scalar
            return
        self.generic_visit(node)

    def _line_value(self, node: ast.AST) -> tuple[str, str] | None:
        if isinstance(node, ast.Call) and _call_name(node.func) == "Line" and len(node.args) >= 2:
            left = node.args[0].id if isinstance(node.args[0], ast.Name) else None
            right = node.args[1].id if isinstance(node.args[1], ast.Name) else None
            if left in self.points and right in self.points:
                return (left, right)
        return None

    def _point_value(self, node: ast.AST | None) -> Point3 | None:
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return self.points.get(node.id)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "array" and node.args:
                return self._point_value(node.args[0])
            if node.func.attr == "make_point_by_coord":
                if len(node.args) < 2:
                    return None
                x_value = self._number_value(node.args[0])
                y_value = self._number_value(node.args[1])
                if x_value is None or y_value is None:
                    return None
                return (float(x_value), float(y_value), 0.0)
            if isinstance(node.func.value, ast.Name) and node.func.attr in {"get_start", "get_end"}:
                line = self.lines.get(node.func.value.id)
                if line:
                    return self.points.get(line[0 if node.func.attr == "get_start" else 1])
        if isinstance(node, ast.BinOp):
            left = self._point_value(node.left)
            right = self._point_value(node.right)
            scalar_left = self._number_value(node.left)
            scalar_right = self._number_value(node.right)
            if isinstance(node.op, ast.Add) and left is not None and right is not None:
                return _point_op(left, right, lambda a, b: a + b)
            if isinstance(node.op, ast.Sub) and left is not None and right is not None:
                return _point_op(left, right, lambda a, b: a - b)
            if isinstance(node.op, ast.Mult):
                if left is not None and scalar_right is not None:
                    return tuple(value * scalar_right for value in left)  # type: ignore[return-value]
                if right is not None and scalar_left is not None:
                    return tuple(value * scalar_left for value in right)  # type: ignore[return-value]
            if isinstance(node.op, ast.Div) and left is not None and scalar_right not in (None, 0):
                return tuple(value / scalar_right for value in left)  # type: ignore[return-value]
        if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) >= 2:
            values = [self._number_value(item) for item in node.elts[:3]]
            if values[0] is None or values[1] is None:
                return None
            z_value = 0.0 if len(values) < 3 or values[2] is None else values[2]
            return (float(values[0]), float(values[1]), float(z_value))
        return None

    def _line_segment_value(self, node: ast.AST | None) -> tuple[Point3, Point3] | None:
        if not isinstance(node, ast.Call) or _call_name(node.func) != "make_line_by_formula":
            return None
        if len(node.args) < 2:
            return None
        slope = self._number_value(node.args[0])
        intercept = self._number_value(node.args[1])
        x_range = self._x_range_from_call(node)
        if slope is None or intercept is None or x_range is None:
            return None
        x1, x2 = x_range
        return ((x1, slope * x1 + intercept, 0.0), (x2, slope * x2 + intercept, 0.0))

    def _x_range_from_call(self, node: ast.Call) -> tuple[float, float] | None:
        for keyword in node.keywords:
            if keyword.arg != "x_range":
                continue
            value = keyword.value
            if isinstance(value, (ast.List, ast.Tuple)) and len(value.elts) >= 2:
                left = self._number_value(value.elts[0])
                right = self._number_value(value.elts[1])
                if left is not None and right is not None:
                    return (float(left), float(right))
        return None

    def _number_value(self, node: ast.AST | None) -> float | None:
        if node is None:
            return None
        if isinstance(node, ast.Name):
            return self.scalars.get(node.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            value = self._number_value(node.operand)
            return -value if value is not None else None
        if isinstance(node, ast.Call) and _call_name(node.func) == "norm" and node.args:
            point = self._point_value(node.args[0])
            if point is not None:
                return math.sqrt(sum(value * value for value in point))
        if isinstance(node, ast.BinOp):
            left = self._number_value(node.left)
            right = self._number_value(node.right)
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


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _point_op(left: Point3, right: Point3, op: Any) -> Point3:
    return tuple(op(a, b) for a, b in zip(left, right, strict=True))  # type: ignore[return-value]


def distance(a: Point3, b: Point3) -> float:
    return math.sqrt(sum((left - right) ** 2 for left, right in zip(a, b, strict=True)))


def point_line_distance(point: Point3, a: Point3, b: Point3) -> float:
    ab = (b[0] - a[0], b[1] - a[1])
    ap = (point[0] - a[0], point[1] - a[1])
    denom = math.hypot(*ab)
    if denom <= 1e-9:
        return float("inf")
    return abs(ab[0] * ap[1] - ab[1] * ap[0]) / denom


def angle_degrees(a: Point3, vertex: Point3, b: Point3) -> float:
    va = (a[0] - vertex[0], a[1] - vertex[1])
    vb = (b[0] - vertex[0], b[1] - vertex[1])
    denom = math.hypot(*va) * math.hypot(*vb)
    if denom <= 1e-9:
        return 0.0
    cosine = max(-1.0, min(1.0, (va[0] * vb[0] + va[1] * vb[1]) / denom))
    return math.degrees(math.acos(cosine))


def reflect_point(point: Point3, a: Point3, b: Point3) -> Point3:
    foot = foot_point(point, a, b)
    return (2 * foot[0] - point[0], 2 * foot[1] - point[1], point[2])


def foot_point(point: Point3, a: Point3, b: Point3) -> Point3:
    ab = (b[0] - a[0], b[1] - a[1])
    denom = ab[0] ** 2 + ab[1] ** 2
    if denom <= 1e-9:
        return point
    t = ((point[0] - a[0]) * ab[0] + (point[1] - a[1]) * ab[1]) / denom
    return (a[0] + t * ab[0], a[1] + t * ab[1], point[2])


def line_intersection(a1: Point3, a2: Point3, b1: Point3, b2: Point3) -> Point3 | None:
    da = (a2[0] - a1[0], a2[1] - a1[1])
    db = (b2[0] - b1[0], b2[1] - b1[1])
    denom = da[0] * db[1] - da[1] * db[0]
    if abs(denom) <= 1e-9:
        return None
    delta = (b1[0] - a1[0], b1[1] - a1[1])
    t = (delta[0] * db[1] - delta[1] * db[0]) / denom
    return (a1[0] + t * da[0], a1[1] + t * da[1], a1[2])
