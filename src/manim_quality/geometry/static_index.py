"""Conservative AST index of initial, statically provable geometry."""

from __future__ import annotations

import ast
from collections.abc import Mapping

from manim_quality.revisions.fingerprint import code_hash

from ._static_ast import (
    assigned_name,
    call_name,
    dynamically_changed_names,
    keyword,
    literal_number,
    literal_vector,
)
from .schemas import GeometrySnapshot, parse_geometry_snapshot
from .source_binding import source_payload


def build_static_geometry_snapshot(
    candidate_code: str,
    *,
    scene_id: str,
) -> GeometrySnapshot:
    if not isinstance(candidate_code, str):
        raise TypeError("candidate_code must be text")
    if not isinstance(scene_id, str) or not scene_id.strip():
        raise ValueError("scene_id must be non-empty text")
    try:
        tree = ast.parse(candidate_code)
    except SyntaxError as error:
        raise ValueError("candidate_code must be valid Python") from error
    construct = _scene_construct(tree, scene_id)
    constants = _module_point_records(candidate_code, scene_id, tree)
    records, counts = _index_assignments(
        candidate_code, scene_id, construct, initial=constants
    )
    _mark_ambiguous_records(records, counts, construct)
    payload = {
        "schema_version": "manim-quality.geometry-snapshot.v1",
        "code_hash": code_hash(candidate_code),
        "scene_id": scene_id,
        "checkpoint_id": "static-initial",
        "provenance": "static_initial_state",
        "objects": sorted(records.values(), key=_record_order),
    }
    return parse_geometry_snapshot(payload)


def _index_assignments(
    code: str,
    scene_id: str,
    construct: ast.FunctionDef,
    *,
    initial: Mapping[str, dict[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, int]]:
    assignments = [
        node
        for node in construct.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
    ]
    records = dict(initial)
    counts: dict[str, int] = {}
    for node in sorted(assignments, key=lambda item: item.lineno):
        name = assigned_name(node)
        if name is None:
            continue
        counts[name] = counts.get(name, 0) + 1
        record = _assignment_record(
            code,
            scene_id,
            name,
            node,
            records,
        )
        if record is not None:
            records[name] = record
    return records, counts


def _module_point_records(
    code: str, scene_id: str, tree: ast.Module
) -> dict[str, dict[str, object]]:
    records: dict[str, dict[str, object]] = {}
    counts: dict[str, int] = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        name = assigned_name(node)
        if name is None:
            continue
        counts[name] = counts.get(name, 0) + 1
        literal = literal_vector(node.value)
        record = (
            _record(
                name,
                "point",
                literal,
                source_payload(code, node, scene_id),
                "position",
            )
            if literal is not None
            else _assignment_record(code, scene_id, name, node, records)
        )
        if record is not None and record["kind"] == "point":
            records[name] = record
    for name, count in counts.items():
        if count > 1 and name in records:
            records[name] = _unknown_record(records[name], "unresolved_reference")
    return records


def _mark_ambiguous_records(
    records: dict[str, dict[str, object]],
    counts: Mapping[str, int],
    construct: ast.FunctionDef,
) -> None:
    for name, count in counts.items():
        if count > 1 and name in records:
            records[name] = _unknown_record(records[name], "unresolved_reference")
    for name in dynamically_changed_names(construct):
        if name in records:
            records[name] = _unknown_record(records[name], "dynamic_value")


def _scene_construct(tree: ast.Module, scene_id: str) -> ast.FunctionDef:
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != scene_id:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "construct":
                return item
        break
    raise ValueError(f"Scene construct not found: {scene_id}")


def _assignment_record(
    code: str,
    scene_id: str,
    name: str,
    node: ast.Assign | ast.AnnAssign,
    records: Mapping[str, dict[str, object]],
) -> dict[str, object] | None:
    value = node.value
    if not isinstance(value, ast.Call):
        return None
    constructor_name = call_name(value.func)
    source = source_payload(code, node, scene_id)
    if constructor_name in {"array", "np.array"}:
        position = literal_vector(value.args[0]) if value.args else None
        return _record(name, "point", position, source, "position")
    constructor = constructor_name.removeprefix("self.")
    if constructor == "Dot":
        position = _resolve_vector(value.args[0], records) if value.args else None
        return _record(name, "point", position, source, "position")
    if constructor in {"Line", "DashedLine"}:
        return _line_record(name, value, source, records)
    if constructor == "Circle":
        return _circle_record(name, value, source)
    if constructor == "Polygon":
        return _polygon_record(name, value, source, records)
    return None


def _record(
    name: str,
    kind: str,
    value: list[int | float] | None,
    source: dict[str, object],
    field: str,
) -> dict[str, object]:
    if value is None:
        return _base_record(name, kind, "unknown", "unresolved_reference", {}, source)
    return _base_record(name, kind, "known", None, {field: value}, source)


def _line_record(
    name: str,
    call: ast.Call,
    source: dict[str, object],
    records: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    if len(call.args) < 2:
        return _base_record(name, "line", "unknown", "unresolved_reference", {}, source)
    start = _resolve_vector(call.args[0], records)
    end = _resolve_vector(call.args[1], records)
    if start is None or end is None:
        return _base_record(name, "line", "unknown", "unresolved_reference", {}, source)
    state: dict[str, object] = {"start": start, "end": end}
    if isinstance(call.args[0], ast.Name):
        state["start_ref"] = call.args[0].id
    if isinstance(call.args[1], ast.Name):
        state["end_ref"] = call.args[1].id
    return _base_record(name, "line", "known", None, state, source)


def _circle_record(
    name: str, call: ast.Call, source: dict[str, object]
) -> dict[str, object]:
    radius_node = keyword(call, "radius")
    radius = literal_number(radius_node) if radius_node is not None else 1.0
    if radius is None or radius <= 0:
        return _base_record(
            name, "circle", "unknown", "unresolved_reference", {}, source
        )
    return _base_record(
        name,
        "circle",
        "known",
        None,
        {"center": [0.0, 0.0, 0.0], "radius": radius},
        source,
    )


def _polygon_record(
    name: str,
    call: ast.Call,
    source: dict[str, object],
    records: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    vertices = [_resolve_vector(item, records) for item in call.args]
    if len(vertices) < 3 or any(item is None for item in vertices):
        return _base_record(
            name, "polygon", "unknown", "unresolved_reference", {}, source
        )
    return _base_record(
        name,
        "polygon",
        "known",
        None,
        {"vertices": [item for item in vertices if item is not None]},
        source,
    )


def _base_record(
    object_id: str,
    kind: str,
    status: str,
    reason_code: str | None,
    state: dict[str, object],
    source: dict[str, object],
) -> dict[str, object]:
    return {
        "object_id": object_id,
        "kind": kind,
        "status": status,
        "reason_code": reason_code,
        "state": state,
        "source": source,
    }


def _unknown_record(
    record: Mapping[str, object], reason_code: str
) -> dict[str, object]:
    return {
        **record,
        "status": "unknown",
        "reason_code": reason_code,
        "state": {},
    }


def _resolve_vector(
    node: ast.AST, records: Mapping[str, dict[str, object]]
) -> list[int | float] | None:
    literal = literal_vector(node)
    if literal is not None:
        return literal
    if not isinstance(node, ast.Name):
        return None
    record = records.get(node.id)
    if record is None or record.get("status") != "known":
        return None
    state = record.get("state")
    if not isinstance(state, Mapping):
        return None
    value = state.get("position")
    return list(value) if isinstance(value, list) else None


def _record_order(record: Mapping[str, object]) -> tuple[int, str]:
    source = record["source"]
    line = source.get("line_start", 0) if isinstance(source, Mapping) else 0
    return int(line), str(record["object_id"])
