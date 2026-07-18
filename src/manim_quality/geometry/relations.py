"""Conservative relation evaluation over an immutable geometry snapshot."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from ._relation_evaluators import EVALUATORS, OPERAND_COUNTS
from .schemas import (
    FACT_SCHEMA_VERSION,
    FactStatus,
    GeometryFact,
    GeometryObject,
    GeometrySnapshot,
    SourceBinding,
    parse_geometry_fact,
)

ENGINE_VERSION = "geometry-inspector-v1"
DEFAULT_TOLERANCE = 1e-6


def inspect_relation(
    snapshot: GeometrySnapshot,
    relation: str,
    operands: Sequence[str],
    *,
    tolerance: float = DEFAULT_TOLERANCE,
) -> GeometryFact:
    if not isinstance(snapshot, GeometrySnapshot):
        raise TypeError("snapshot must be GeometrySnapshot")
    if not isinstance(relation, str) or not relation.strip():
        raise ValueError("relation must be non-empty text")
    _validate_tolerance(tolerance)
    evaluator = EVALUATORS.get(relation)
    if evaluator is None:
        return _unknown(snapshot, relation, (), "unsupported_relation")
    resolved, failure = _resolve(snapshot, operands)
    if failure is not None:
        return _unknown(snapshot, relation, resolved, failure)
    if len(resolved) != OPERAND_COUNTS[relation]:
        return _unknown(snapshot, relation, resolved, "unsupported_relation")
    outcome, observed = evaluator(resolved, float(tolerance))
    if isinstance(outcome, str):
        return _unknown(snapshot, relation, resolved, outcome, observed)
    return _known(snapshot, relation, resolved, outcome, observed)


def _validate_tolerance(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        or value > 0.1
    ):
        raise ValueError("tolerance must be finite and in (0, 0.1]")


def _resolve(
    snapshot: GeometrySnapshot, operands: Sequence[str]
) -> tuple[tuple[GeometryObject, ...], str | None]:
    if isinstance(operands, (str, bytes)) or not isinstance(operands, Sequence):
        raise TypeError("operands must be a sequence of object IDs")
    resolved: list[GeometryObject] = []
    for value in operands:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("operand IDs must be non-empty text")
        try:
            item = snapshot.object(value)
        except KeyError:
            return tuple(resolved), "missing_entity"
        resolved.append(item)
        if item.status is FactStatus.UNKNOWN:
            return tuple(resolved), item.reason_code or "unresolved_reference"
    return tuple(resolved), None


def _known(
    snapshot: GeometrySnapshot,
    relation: str,
    objects: Sequence[GeometryObject],
    truth: bool,
    observed: Mapping[str, object],
) -> GeometryFact:
    return _fact(snapshot, relation, objects, truth, observed, None)


def _unknown(
    snapshot: GeometrySnapshot,
    relation: str,
    objects: Sequence[GeometryObject],
    reason: str,
    observed: Mapping[str, object] | None = None,
) -> GeometryFact:
    return _fact(snapshot, relation, objects, None, observed or {}, reason)


def _fact(
    snapshot: GeometrySnapshot,
    relation: str,
    objects: Sequence[GeometryObject],
    truth: bool | None,
    observed: Mapping[str, object],
    reason: str | None,
) -> GeometryFact:
    evidence = _evidence(objects)
    return parse_geometry_fact(
        {
            "schema_version": FACT_SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "code_hash": snapshot.code_hash,
            "snapshot_hash": snapshot.snapshot_hash,
            "relation": relation,
            "status": "known" if truth is not None else "unknown",
            "truth": truth,
            "observed": dict(observed),
            "evidence": [_source_payload(item) for item in evidence],
            "assumptions": [],
            "reason_code": reason,
        }
    )


def _source_payload(item: SourceBinding) -> dict[str, object]:
    return {
        "scene_id": item.scene_id,
        "line_start": item.line_start,
        "line_end": item.line_end,
        "excerpt": item.excerpt,
    }


def _evidence(objects: Sequence[GeometryObject]) -> tuple[SourceBinding, ...]:
    by_key = {
        (
            item.source.scene_id,
            item.source.line_start,
            item.source.line_end,
        ): item.source
        for item in objects
    }
    return tuple(by_key[key] for key in sorted(by_key))
