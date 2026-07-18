"""Conservative symbolic index for named geometry in one Scene."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from manim_quality.geometry._static_ast import (
    assigned_name,
    call_name,
    dynamically_changed_names,
    literal_vector,
)

Vector = tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SymbolicPoint:
    object_id: str
    position: Vector | None
    line_start: int


@dataclass(frozen=True, slots=True)
class SymbolicLine:
    object_id: str
    start_ref: str | None
    end_ref: str | None
    start: Vector | None
    end: Vector | None
    line_start: int


@dataclass(frozen=True, slots=True)
class SymbolicGeometryIndex:
    points: dict[str, SymbolicPoint]
    lines: dict[str, SymbolicLine]

    def resolve_named_line(self, name: str) -> SymbolicLine | None:
        matches = self.find_named_lines(name)
        return matches[0] if matches else None

    def find_named_lines(self, name: str) -> tuple[SymbolicLine, ...]:
        normalized = _normalize_line_name(name)
        return tuple(
            item
            for key, item in self.lines.items()
            if _normalize_line_name(key) == normalized
        )

    def resolve_segment(self, name: str) -> SymbolicLine | None:
        named = self.resolve_named_line(name)
        if named is not None:
            return named if named.start is not None and named.end is not None else None
        point_names = _point_pair(name)
        if point_names is None:
            return None
        left, right = (self.points.get(item) for item in point_names)
        if (
            left is None
            or right is None
            or left.position is None
            or right.position is None
        ):
            return None
        return SymbolicLine(
            object_id=name,
            start_ref=left.object_id,
            end_ref=right.object_id,
            start=left.position,
            end=right.position,
            line_start=min(left.line_start, right.line_start),
        )


def build_symbolic_index(code: str, *, scene_id: str) -> SymbolicGeometryIndex:
    tree = ast.parse(code)
    construct = _construct(tree, scene_id)
    dynamic = dynamically_changed_names(construct)
    points: dict[str, SymbolicPoint] = {}
    lines: dict[str, SymbolicLine] = {}
    for node in construct.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        name = assigned_name(node)
        if name is None:
            continue
        point = _point(node, name, dynamic)
        if point is not None:
            points[name] = point
            continue
        line = _line(node, name, points)
        if line is not None:
            lines[name] = line
    return SymbolicGeometryIndex(points, lines)


def _construct(tree: ast.Module, scene_id: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == scene_id:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "construct":
                    return item
    raise ValueError(f"Scene construct not found: {scene_id}")


def _point(
    node: ast.Assign | ast.AnnAssign, name: str, dynamic: set[str]
) -> SymbolicPoint | None:
    value = node.value
    vector = literal_vector(value)
    if isinstance(value, ast.Call) and call_name(value.func) in {"array", "np.array"}:
        vector = literal_vector(value.args[0]) if value.args else None
    elif (
        isinstance(value, ast.Call)
        and call_name(value.func).removeprefix("self.") == "Dot"
    ):
        vector = literal_vector(value.args[0]) if value.args else None
    if vector is None:
        return None
    position = None if name in dynamic else tuple(float(item) for item in vector)
    return SymbolicPoint(name, position, node.lineno)


def _line(
    node: ast.Assign | ast.AnnAssign,
    name: str,
    points: dict[str, SymbolicPoint],
) -> SymbolicLine | None:
    value = node.value
    if not isinstance(value, ast.Call):
        return None
    constructor = call_name(value.func).removeprefix("self.")
    if constructor not in {"Line", "DashedLine", "Arrow", "DoubleArrow"}:
        return None
    start_node = _argument(value, 0, "start")
    end_node = _argument(value, 1, "end")
    start_ref, end_ref = _reference(start_node), _reference(end_node)
    return SymbolicLine(
        name,
        start_ref,
        end_ref,
        _position(start_node, points),
        _position(end_node, points),
        node.lineno,
    )


def _argument(call: ast.Call, index: int, keyword: str) -> ast.AST | None:
    if len(call.args) > index:
        return call.args[index]
    return next((item.value for item in call.keywords if item.arg == keyword), None)


def _reference(node: ast.AST | None) -> str | None:
    return node.id if isinstance(node, ast.Name) else None


def _position(node: ast.AST | None, points: dict[str, SymbolicPoint]) -> Vector | None:
    literal = literal_vector(node) if node is not None else None
    if literal is not None:
        return tuple(float(item) for item in literal)
    ref = _reference(node)
    return points[ref].position if ref in points else None


def _normalize_line_name(value: str) -> str:
    name = value.strip().lower()
    for prefix in ("line_", "segment_", "edge_", "dashed_"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    name = name.replace("_", "")
    return "".join(sorted(name)) if len(name) == 2 and name.isalpha() else name


def _point_pair(value: str) -> tuple[str, str] | None:
    name = value.strip()
    if ":" in name:
        parts = tuple(item.strip() for item in name.split(":"))
        if len(parts) == 2 and all(parts):
            return parts
    if len(name) == 2 and name.isalpha() and name.upper() == name:
        return name[0], name[1]
    return None
