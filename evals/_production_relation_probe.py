"""Adapters for replaying deterministic production geometry contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from manim_quality.logic.expectations.schemas import SCHEMA_VERSION


def contract_payload(
    case_id: str, contracts: Sequence[Mapping[str, object]]
) -> dict[str, object]:
    claims = []
    for index, contract in enumerate(contracts, start=1):
        relation, operands = _relation(contract)
        claims.append(
            {
                "claim_id": f"{case_id}-{index}",
                "relation": relation,
                "operands": operands,
                "source_kind": "plan",
                "evidence": "frozen deterministic production contract",
                "confidence": "explicit",
            }
        )
    return {"schema_version": SCHEMA_VERSION, "claims": claims}


def _relation(contract: Mapping[str, object]) -> tuple[str, list[str]]:
    kind = contract.get("kind")
    if kind == "intersection":
        return "intersection", [
            _text(contract, "point"),
            _segment(contract, "line1_points"),
            _segment(contract, "line2_points"),
        ]
    if kind == "distance_between_points":
        return "segment_length", [
            _segment(contract, "points"),
            _number(contract, "expected_length"),
        ]
    if kind == "point_coordinate":
        return "point_coordinate", [
            _text(contract, "point"),
            *_numbers(contract, "expected_coords", count=3),
        ]
    if kind == "perpendicular_lines":
        return "perpendicular", [
            _segment(contract, "line1_points"),
            _segment(contract, "line2_points"),
        ]
    if kind == "collinearity_model":
        line = _texts(contract, "line_points", count=2)
        return "collinear", [line[0], _text(contract, "point"), line[1]]
    raise ValueError(f"unsupported production contract kind: {kind}")


def _segment(contract: Mapping[str, object], field: str) -> str:
    points = _texts(contract, field, count=2)
    if all(len(point) == 1 and point.isalpha() and point.isupper() for point in points):
        return "".join(points)
    return ":".join(points)


def _texts(
    contract: Mapping[str, object], field: str, *, count: int
) -> list[str]:
    value = contract.get(field)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be an array")
    result = [str(item).strip() for item in value]
    if len(result) != count or any(not item for item in result):
        raise ValueError(f"{field} has invalid values")
    return result


def _numbers(
    contract: Mapping[str, object], field: str, *, count: int
) -> list[str]:
    values = _texts(contract, field, count=count)
    for value in values:
        float(value)
    return values


def _number(contract: Mapping[str, object], field: str) -> str:
    value = contract.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    return str(value)


def _text(contract: Mapping[str, object], field: str) -> str:
    value = contract.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    return value.strip()
