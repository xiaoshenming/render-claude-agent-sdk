"""Strict, immutable contracts for facts-only geometry inspection."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from manim_quality.contracts._formats import require_sha256
from manim_quality.contracts._json_values import (
    freeze_wire_json_object,
    thaw_json_object,
)
from manim_quality.contracts._validation import require_non_empty_string
from manim_quality.revisions.fingerprint import sha256_text

from ._contract_safety import reject_forbidden
from ._state_validation import validate_fact_content, validate_object_state

SNAPSHOT_SCHEMA_VERSION = "manim-quality.geometry-snapshot.v1"
FACT_SCHEMA_VERSION = "manim-quality.geometry-fact.v1"
MAX_EXCERPT_CHARS = 500

_SNAPSHOT_FIELDS = frozenset(
    {
        "schema_version",
        "code_hash",
        "scene_id",
        "checkpoint_id",
        "provenance",
        "objects",
    }
)
_OBJECT_FIELDS = frozenset(
    {"object_id", "kind", "status", "reason_code", "state", "source"}
)
_SOURCE_FIELDS = frozenset({"scene_id", "line_start", "line_end", "excerpt"})
_FACT_FIELDS = frozenset(
    {
        "schema_version",
        "engine_version",
        "code_hash",
        "snapshot_hash",
        "relation",
        "status",
        "truth",
        "observed",
        "evidence",
        "assumptions",
        "reason_code",
    }
)
_OBJECT_KINDS = frozenset({"point", "line", "circle", "polygon"})
_PROVENANCE = frozenset({"runtime_checkpoint", "runtime_final", "static_initial_state"})
_UNKNOWN_REASONS = frozenset(
    {
        "ambiguous_space",
        "dynamic_value",
        "missing_entity",
        "timeout",
        "unresolved_reference",
        "unsupported_object",
        "unsupported_relation",
    }
)


class FactStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceBinding:
    scene_id: str
    line_start: int
    line_end: int
    excerpt: str


@dataclass(frozen=True, slots=True)
class GeometryObject:
    object_id: str
    kind: str
    status: FactStatus
    reason_code: str | None
    state: Mapping[str, object]
    source: SourceBinding


@dataclass(frozen=True, slots=True)
class GeometrySnapshot:
    code_hash: str
    scene_id: str
    checkpoint_id: str
    provenance: str
    objects: tuple[GeometryObject, ...]
    _wire: Mapping[str, object]

    @property
    def snapshot_hash(self) -> str:
        canonical = json.dumps(
            thaw_json_object(self._wire),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256_text(canonical)

    def object(self, object_id: str) -> GeometryObject:
        key = require_non_empty_string(object_id, "object_id")
        for item in self.objects:
            if item.object_id == key:
                return item
        raise KeyError(key)


@dataclass(frozen=True, slots=True)
class GeometryFact:
    engine_version: str
    code_hash: str
    snapshot_hash: str
    relation: str
    status: FactStatus
    truth: bool | None
    observed: Mapping[str, object]
    evidence: tuple[SourceBinding, ...]
    assumptions: tuple[str, ...]
    reason_code: str | None


def parse_geometry_snapshot(value: object) -> GeometrySnapshot:
    data = _wire_object(value, _SNAPSHOT_FIELDS, "geometry snapshot")
    if data["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("geometry snapshot schema_version is unsupported")
    require_sha256(data["code_hash"], "geometry snapshot code_hash")
    scene_id = require_non_empty_string(data["scene_id"], "scene_id")
    checkpoint_id = require_non_empty_string(data["checkpoint_id"], "checkpoint_id")
    provenance = require_non_empty_string(data["provenance"], "provenance")
    if provenance not in _PROVENANCE:
        raise ValueError("geometry snapshot provenance is unsupported")
    raw_objects = _array(data["objects"], "objects")
    objects = tuple(_parse_object(item, scene_id) for item in raw_objects)
    identifiers = [item.object_id for item in objects]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("geometry snapshot contains duplicate object_id values")
    return GeometrySnapshot(
        code_hash=data["code_hash"],
        scene_id=scene_id,
        checkpoint_id=checkpoint_id,
        provenance=provenance,
        objects=objects,
        _wire=freeze_wire_json_object(value, "geometry snapshot"),
    )


def parse_geometry_fact(value: object) -> GeometryFact:
    data = _wire_object(value, _FACT_FIELDS, "geometry fact")
    if data["schema_version"] != FACT_SCHEMA_VERSION:
        raise ValueError("geometry fact schema_version is unsupported")
    engine = require_non_empty_string(data["engine_version"], "engine_version")
    code_hash = require_sha256(data["code_hash"], "geometry fact code_hash")
    snapshot_hash = require_sha256(data["snapshot_hash"], "geometry fact snapshot_hash")
    relation = require_non_empty_string(data["relation"], "relation")
    status = _status(data["status"])
    truth = data["truth"]
    reason = _optional_reason(data["reason_code"])
    _validate_status(status, truth, reason, "geometry fact")
    observed = freeze_wire_json_object(data["observed"], "observed")
    reject_forbidden(observed, "observed")
    evidence = tuple(
        _parse_source(item) for item in _array(data["evidence"], "evidence")
    )
    assumptions = tuple(
        require_non_empty_string(item, f"assumptions[{index}]")
        for index, item in enumerate(_array(data["assumptions"], "assumptions"))
    )
    validate_fact_content(relation, observed, assumptions)
    return GeometryFact(
        engine_version=engine,
        code_hash=code_hash,
        snapshot_hash=snapshot_hash,
        relation=relation,
        status=status,
        truth=truth,
        observed=observed,
        evidence=evidence,
        assumptions=assumptions,
        reason_code=reason,
    )


def _parse_object(value: object, scene_id: str) -> GeometryObject:
    data = _wire_object(value, _OBJECT_FIELDS, "geometry object")
    object_id = require_non_empty_string(data["object_id"], "object_id")
    kind = require_non_empty_string(data["kind"], "kind")
    if kind not in _OBJECT_KINDS:
        raise ValueError(f"unsupported geometry object kind: {kind}")
    status = _status(data["status"])
    reason = _optional_reason(data["reason_code"])
    state = freeze_wire_json_object(data["state"], "geometry object state")
    reject_forbidden(state, "geometry object state")
    _validate_status(
        status, True if status is FactStatus.KNOWN else None, reason, "geometry object"
    )
    if status is FactStatus.KNOWN and not state:
        raise ValueError("known geometry object requires non-empty state")
    validate_object_state(kind, known=status is FactStatus.KNOWN, state=state)
    source = _parse_source(data["source"])
    if source.scene_id != scene_id:
        raise ValueError("geometry object source scene must match snapshot scene")
    return GeometryObject(object_id, kind, status, reason, state, source)


def _parse_source(value: object) -> SourceBinding:
    data = _wire_object(value, _SOURCE_FIELDS, "source binding")
    scene_id = require_non_empty_string(data["scene_id"], "source scene_id")
    start = _positive_int(data["line_start"], "line_start")
    end = _positive_int(data["line_end"], "line_end")
    if end < start:
        raise ValueError("source line_end must not precede line_start")
    excerpt = require_non_empty_string(data["excerpt"], "source excerpt")
    if len(excerpt) > MAX_EXCERPT_CHARS:
        raise ValueError("source excerpt exceeds maximum length")
    return SourceBinding(scene_id, start, end, excerpt)


def _wire_object(value: object, fields: frozenset[str], name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError(f"{name} must be a JSON object")
    if value.keys() != fields:
        raise ValueError(f"{name} fields do not match contract")
    return value


def _array(value: object, name: str) -> Sequence[object]:
    if type(value) is not list:
        raise TypeError(f"{name} must be a JSON array")
    return value


def _status(value: object) -> FactStatus:
    if type(value) is not str:
        raise TypeError("status must be a string")
    try:
        return FactStatus(value)
    except ValueError as error:
        raise ValueError(f"unsupported geometry status: {value!r}") from error


def _optional_reason(value: object) -> str | None:
    if value is None:
        return None
    reason = require_non_empty_string(value, "reason_code")
    if reason not in _UNKNOWN_REASONS:
        raise ValueError(f"unsupported reason_code: {reason}")
    return reason


def _validate_status(
    status: FactStatus,
    truth: object,
    reason: str | None,
    name: str,
) -> None:
    if status is FactStatus.KNOWN:
        if type(truth) is not bool:
            raise ValueError(f"known {name} requires boolean truth")
        if reason is not None:
            raise ValueError(f"known {name} cannot declare reason_code")
        return
    if truth is not None:
        raise ValueError(f"unknown {name} requires null truth")
    if reason is None:
        raise ValueError(f"unknown {name} requires reason_code")


def _positive_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value
