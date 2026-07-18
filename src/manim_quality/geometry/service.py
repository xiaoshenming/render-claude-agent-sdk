"""Facts-only application service over one immutable geometry snapshot."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from manim_quality.contracts._json_values import thaw_json_object

from .relations import inspect_relation
from .schemas import GeometryFact, GeometrySnapshot, SourceBinding

SUPPORTED_RELATIONS = frozenset(
    {
        "collinear",
        "equal_length",
        "line_endpoints",
        "midpoint",
        "parallel",
        "perpendicular",
        "point_on_circle",
        "point_on_line",
    }
)
MAX_TOOL_EXCERPT_CHARS = 160
RELATION_OPERAND_COUNTS = {
    name: 3 if name in {"collinear", "line_endpoints", "midpoint"} else 2
    for name in SUPPORTED_RELATIONS
}


@dataclass(frozen=True, slots=True)
class GeometryInspector:
    snapshot: GeometrySnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, GeometrySnapshot):
            raise TypeError("snapshot must be GeometrySnapshot")

    def inspect(self, arguments: Mapping[str, object]) -> Mapping[str, object]:
        relation, operands = validate_inspection_arguments(arguments)
        fact = inspect_relation(self.snapshot, relation, operands)
        return _fact_payload(fact, self.snapshot.provenance)

    def inspect_json(self, arguments: Mapping[str, object]) -> str:
        return json.dumps(
            self.inspect(arguments),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def validate_inspection_arguments(
    arguments: Mapping[str, object],
) -> tuple[str, tuple[str, ...]]:
    if not isinstance(arguments, Mapping):
        raise TypeError("geometry inspection arguments must be an object")
    if set(arguments) != {"relation", "operands"}:
        raise ValueError("geometry inspection accepts only relation and operands")
    relation = arguments["relation"]
    if not isinstance(relation, str) or relation not in SUPPORTED_RELATIONS:
        raise ValueError("unsupported geometry relation")
    raw_operands = arguments["operands"]
    if not isinstance(raw_operands, (list, tuple)):
        raise TypeError("operands must be an array of logical object IDs")
    expected_count = RELATION_OPERAND_COUNTS[relation]
    if len(raw_operands) != expected_count:
        raise ValueError(f"{relation} requires exactly {expected_count} operands")
    if any(not isinstance(item, str) or not item.strip() for item in raw_operands):
        raise ValueError("operand IDs must be non-empty strings")
    return relation, tuple(raw_operands)


def _fact_payload(fact: GeometryFact, provenance: str) -> dict[str, object]:
    return {
        "engine_version": fact.engine_version,
        "code_hash": fact.code_hash,
        "snapshot_hash": fact.snapshot_hash,
        "snapshot_provenance": provenance,
        "relation": fact.relation,
        "status": fact.status.value,
        "truth": fact.truth,
        "observed": thaw_json_object(fact.observed),
        "evidence": [_source_payload(item) for item in fact.evidence],
        "assumptions": list(fact.assumptions) + _provenance_assumptions(provenance),
        "reason_code": fact.reason_code,
    }


def _source_payload(item: SourceBinding) -> dict[str, object]:
    return {
        "scene_id": item.scene_id,
        "line_start": item.line_start,
        "line_end": item.line_end,
        "excerpt": item.excerpt[:MAX_TOOL_EXCERPT_CHARS],
    }


def _provenance_assumptions(provenance: str) -> list[str]:
    if provenance == "runtime_final":
        return []
    if provenance == "runtime_checkpoint":
        return ["checkpoint-scoped-observation"]
    return ["static-initial-state-only", "dynamic-transforms-not-proven"]
