"""Deterministic comparison of expected and symbolic candidate relations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .numeric_comparison import compare_numeric_relation, source_lines, unique_lines
from .schemas import ExpectedRelationClaim, ExpectedRelationContract
from .symbolic_index import SymbolicGeometryIndex


class ComparisonStatus(StrEnum):
    SATISFIED = "satisfied"
    CONTRADICTION = "contradiction"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RelationComparison:
    claim: ExpectedRelationClaim
    status: ComparisonStatus
    actual: dict[str, object]
    reason_code: str | None
    candidate_lines: tuple[int, ...]


def compare_expected_relations(
    contract: ExpectedRelationContract,
    index: SymbolicGeometryIndex,
) -> tuple[RelationComparison, ...]:
    return tuple(_compare(claim, index) for claim in contract.claims)


def _compare(
    claim: ExpectedRelationClaim, index: SymbolicGeometryIndex
) -> RelationComparison:
    if claim.relation == "line_endpoints":
        return _line_endpoints(claim, index)
    mismatch = _semantic_segment_mismatch(claim, index)
    if mismatch is not None:
        return mismatch
    outcome, actual, lines = compare_numeric_relation(claim, index)
    if outcome is None:
        return RelationComparison(
            claim, ComparisonStatus.UNKNOWN, actual, "missing_entity", ()
        )
    status = ComparisonStatus.SATISFIED if outcome else ComparisonStatus.CONTRADICTION
    return RelationComparison(claim, status, actual, None, lines)


def _line_endpoints(
    claim: ExpectedRelationClaim, index: SymbolicGeometryIndex
) -> RelationComparison:
    lines = index.find_named_lines(claim.operands[0])
    if not lines:
        return RelationComparison(
            claim, ComparisonStatus.UNKNOWN, {}, "missing_entity", ()
        )
    expected = claim.operands[1:]
    normalized_expected = tuple(_semantic_point(item) for item in expected)
    for line in lines:
        if line.start_ref is None or line.end_ref is None:
            continue
        actual = {"start_ref": line.start_ref, "end_ref": line.end_ref}
        normalized_actual = tuple(
            _semantic_point(item) for item in (line.start_ref, line.end_ref)
        )
        matches = normalized_actual in {
            normalized_expected,
            normalized_expected[::-1],
        }
        if not matches:
            return RelationComparison(
                claim,
                ComparisonStatus.CONTRADICTION,
                actual,
                None,
                (line.line_start,),
            )
    known = tuple(
        line
        for line in lines
        if line.start_ref is not None and line.end_ref is not None
    )
    if not known:
        return RelationComparison(
            claim, ComparisonStatus.UNKNOWN, {}, "missing_entity", ()
        )
    return RelationComparison(
        claim,
        ComparisonStatus.SATISFIED,
        {"representations_checked": len(known)},
        None,
        unique_lines(*(line.line_start for line in known)),
    )


def _semantic_segment_mismatch(
    claim: ExpectedRelationClaim, index: SymbolicGeometryIndex
) -> RelationComparison | None:
    operands = (
        claim.operands[1:]
        if claim.relation == "point_on_line"
        else claim.operands
    )
    for operand in operands:
        expected = _point_pair(operand)
        lines = index.find_named_lines(operand)
        if expected is None or not lines:
            continue
        for line in lines:
            actual = (line.start_ref, line.end_ref)
            if None in actual:
                continue
            normalized_actual = tuple(_semantic_point(item) for item in actual)
            if normalized_actual not in {expected, expected[::-1]}:
                return RelationComparison(
                    claim,
                    ComparisonStatus.CONTRADICTION,
                    {
                        "semantic_segment": operand,
                        "start_ref": line.start_ref,
                        "end_ref": line.end_ref,
                    },
                    None,
                    source_lines(index, line),
                )
    return None


def _point_pair(value: str) -> tuple[str, str] | None:
    name = value.strip()
    if len(name) == 2 and name.isalpha() and name.upper() == name:
        return name[0], name[1]
    return None


def _semantic_point(value: str | None) -> str:
    name = (value or "").strip()
    if len(name) == 2 and name[0].lower() == "p" and name[1].isalpha():
        name = name[1]
    for prefix in ("point_", "p_", "pt_"):
        if name.lower().startswith(prefix):
            name = name[len(prefix) :]
            break
    for suffix in ("_point", "_pos", "_pt"):
        if name.lower().endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name.upper() if len(name) == 1 and name.isalpha() else name
