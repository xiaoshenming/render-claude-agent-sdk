"""Strict contracts for mathematical relations stated by source material."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

SCHEMA_VERSION = "manim-quality.expected-relations.v1"
OPERAND_COUNTS = {
    "collinear": 3,
    "equal_length": 2,
    "intersection": 3,
    "line_endpoints": 3,
    "midpoint": 3,
    "parallel": 2,
    "perpendicular": 2,
    "point_coordinate": 4,
    "point_on_line": 2,
    "segment_length": 2,
}
SOURCE_KINDS = frozenset({"problem", "solution", "plan"})
CONFIDENCE_LEVELS = frozenset({"explicit", "derived"})
_CLAIM_FIELDS = frozenset(
    {"claim_id", "relation", "operands", "source_kind", "evidence", "confidence"}
)


@dataclass(frozen=True, slots=True)
class ExpectedRelationClaim:
    claim_id: str
    relation: str
    operands: tuple[str, ...]
    source_kind: str
    evidence: str
    confidence: str


@dataclass(frozen=True, slots=True)
class ExpectedRelationContract:
    schema_version: str
    claims: tuple[ExpectedRelationClaim, ...]


def parse_expected_relation_contract(
    payload: Mapping[str, object],
) -> ExpectedRelationContract:
    if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "claims"}:
        raise ValueError("expected relation contract fields are invalid")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported expected relation schema")
    raw_claims = payload["claims"]
    if isinstance(raw_claims, (str, bytes)) or not isinstance(raw_claims, Sequence):
        raise ValueError("claims must be an array")
    claims = tuple(_parse_claim(item) for item in raw_claims)
    ids = [item.claim_id for item in claims]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate claim_id")
    return ExpectedRelationContract(SCHEMA_VERSION, claims)


def _parse_claim(value: object) -> ExpectedRelationClaim:
    if not isinstance(value, Mapping) or set(value) != _CLAIM_FIELDS:
        raise ValueError("expected relation claim fields are invalid")
    claim_id = _text(value["claim_id"], "claim_id")
    relation = _text(value["relation"], "relation")
    if relation not in OPERAND_COUNTS:
        raise ValueError("unsupported expected relation")
    operands = _operands(value["operands"], OPERAND_COUNTS[relation])
    _validate_numeric_operands(relation, operands)
    source_kind = _choice(value["source_kind"], SOURCE_KINDS, "source_kind")
    evidence = _text(value["evidence"], "evidence")
    confidence = _choice(value["confidence"], CONFIDENCE_LEVELS, "confidence")
    return ExpectedRelationClaim(
        claim_id, relation, operands, source_kind, evidence, confidence
    )


def _operands(value: object, count: int) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("operands must be an array")
    operands = tuple(_text(item, "operand") for item in value)
    if len(operands) != count:
        raise ValueError("operand count does not match relation")
    return operands


def _choice(value: object, allowed: frozenset[str], name: str) -> str:
    result = _text(value, name)
    if result not in allowed:
        raise ValueError(f"invalid {name}")
    return result


def _validate_numeric_operands(relation: str, operands: tuple[str, ...]) -> None:
    values = operands[1:] if relation == "point_coordinate" else operands[1:2]
    if relation not in {"point_coordinate", "segment_length"}:
        return
    try:
        numeric = tuple(float(value) for value in values)
    except ValueError as error:
        raise ValueError("numeric relation operands must be finite numbers") from error
    if not all(math.isfinite(value) for value in numeric):
        raise ValueError("numeric relation operands must be finite numbers")


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def expected_relation_output_schema() -> dict[str, object]:
    claim = {
        "type": "object",
        "properties": {
            "claim_id": {"type": "string", "minLength": 1},
            "relation": {"type": "string", "enum": sorted(OPERAND_COUNTS)},
            "operands": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
                "minItems": 2,
                "maxItems": 4,
            },
            "source_kind": {"type": "string", "enum": sorted(SOURCE_KINDS)},
            "evidence": {"type": "string", "minLength": 1},
            "confidence": {
                "type": "string",
                "enum": sorted(CONFIDENCE_LEVELS),
            },
        },
        "required": sorted(_CLAIM_FIELDS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "schema_version": {"type": "string", "enum": [SCHEMA_VERSION]},
            "claims": {"type": "array", "items": claim, "maxItems": 40},
        },
        "required": ["schema_version", "claims"],
        "additionalProperties": False,
    }
