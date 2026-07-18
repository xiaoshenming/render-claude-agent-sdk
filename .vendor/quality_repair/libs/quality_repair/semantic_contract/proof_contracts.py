"""Proof-claim contract orchestration."""

from __future__ import annotations

from typing import Any, Callable

from .geometry_facts import extract_geometry_facts, foot_point, line_intersection
from .geometry_math import distance_tuple, reflect_point
from .proof_claims import extract_proof_claims
from .proof_rules import (
    angle_equals_angle_contract,
    angle_equals_degrees_contract,
    foot_point_contract,
    length_equals_length_contract,
    line_intersection_contract,
    line_perpendicular_contract,
    points_collinear_contract,
)
from .source_utils import line_number_containing, source_line
from .suggestions import array_assignment_suggested_replacement

Rule = Callable[[Any, Any], tuple[dict[str, Any] | None, dict[str, Any] | None]]

RULES: dict[str, Rule] = {
    "foot_point": foot_point_contract,
    "line_intersection": line_intersection_contract,
    "points_collinear": points_collinear_contract,
    "line_perpendicular": line_perpendicular_contract,
    "angle_equals_degrees": angle_equals_degrees_contract,
    "angle_equals_angle": angle_equals_angle_contract,
    "length_equals_length": length_equals_length_contract,
}


def proof_claim_contracts(source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    facts = extract_geometry_facts(source)
    contracts: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for claim in extract_proof_claims(source):
        rule = RULES.get(claim.kind)
        if not rule:
            continue
        _append_pair(rule(claim, facts), contracts, findings, seen)
    for pair in reflection_shortest_path_template_contracts(source, facts):
        _append_pair(pair, contracts, findings, seen)
    return contracts, findings


def _append_pair(
    pair: tuple[dict[str, Any] | None, dict[str, Any] | None],
    contracts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
) -> None:
    contract, finding = pair
    if not contract or not finding:
        return
    key = (
        contract.get("kind"),
        contract.get("target"),
        tuple(contract.get("points") or []),
        tuple(contract.get("line_a") or []),
        tuple(contract.get("line_b") or []),
        contract.get("claim_text"),
    )
    if key in seen:
        return
    seen.add(key)
    contracts.append(contract)
    findings.append(finding)


def reflection_shortest_path_template_contracts(source: str, facts: Any) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    compact_source = source.replace(" ", "")
    if not (
        ("B'、M、N共线" in compact_source or "B',M,N共线" in compact_source)
        and ("B'N⊥AB" in compact_source or "B'N垂直于AB" in compact_source)
    ):
        return []
    required = {
        "A": facts.resolve_point("A"),
        "B": facts.resolve_point("B"),
        "D": facts.resolve_point("D"),
        "B_prime": facts.resolve_point("B'"),
        "M_rand": facts.resolve_point("M"),
        "N_rand": facts.resolve_point("N"),
    }
    if not all(required.values()):
        return []
    a, b, d = required["A"], required["B"], required["D"]
    b_prime, m_rand, n_rand = required["B_prime"], required["M_rand"], required["N_rand"]
    assert a and b and d and b_prime and m_rand and n_rand
    line_no = line_number_containing(source, "B'N") or facts.lines_by_name.get(n_rand) or facts.lines_by_name.get(m_rand) or 1
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    expected_b_prime = reflect_point(facts.points[b], facts.points[a], facts.points[d])
    foot_expected = foot_point(expected_b_prime, facts.points[a], facts.points[b])
    if distance_tuple(facts.points[n_rand], foot_expected) > 1e-3:
        pairs.append(_shortest_path_foot_pair(source, facts, b_prime, n_rand, a, b, line_no, foot_expected))
    intersection_expected = line_intersection(facts.points[a], facts.points[d], expected_b_prime, foot_expected)
    if intersection_expected is not None and distance_tuple(facts.points[m_rand], intersection_expected) > 1e-3:
        pairs.append(_shortest_path_intersection_pair(source, facts, b_prime, m_rand, n_rand, a, d, line_no, intersection_expected))
    return pairs


def _shortest_path_foot_pair(
    source: str,
    facts: Any,
    b_prime: str,
    n_rand: str,
    a: str,
    b: str,
    line_no: int,
    expected: tuple[float, float, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = {
        "kind": "foot_point",
        "target": n_rand,
        "source": b_prime,
        "line": [a, b],
        "source_line": facts.lines_by_name.get(n_rand) or line_no,
        "expected_coords": list(expected),
        "actual_coords": list(facts.points[n_rand]),
        "claim_text": source_line(source, line_no).strip(),
        "suggested_replacement": array_assignment_suggested_replacement(n_rand, expected),
        "repair_hint": f"Shortest-path template: set {n_rand} to the perpendicular foot from {b_prime} to {a}{b}.",
        "label": f"{n_rand} is foot of {b_prime} to {a}{b}",
    }
    return contract, {**contract, "kind": "foot_point_mismatch"}


def _shortest_path_intersection_pair(
    source: str,
    facts: Any,
    b_prime: str,
    m_rand: str,
    n_rand: str,
    a: str,
    d: str,
    line_no: int,
    expected: tuple[float, float, float],
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = {
        "kind": "line_intersection",
        "target": m_rand,
        "line_a": [a, d],
        "line_b": [b_prime, n_rand],
        "source_line": facts.lines_by_name.get(m_rand) or line_no,
        "expected_coords": list(expected),
        "actual_coords": list(facts.points[m_rand]),
        "claim_text": source_line(source, line_no).strip(),
        "suggested_replacement": array_assignment_suggested_replacement(m_rand, expected),
        "repair_hint": f"Shortest-path template: set {m_rand} to intersection of {a}{d} and {b_prime}{n_rand}.",
        "label": f"{m_rand} is intersection of {a}{d} and {b_prime}{n_rand}",
    }
    return contract, {**contract, "kind": "line_intersection_mismatch"}
