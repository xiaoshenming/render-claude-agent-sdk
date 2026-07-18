"""Proof-claim contract rules."""

from __future__ import annotations

from typing import Any

from .geometry_facts import (
    angle_degrees as fact_angle_degrees,
    distance as fact_distance,
    foot_point as fact_foot_point,
    line_intersection as fact_line_intersection,
    point_line_distance as fact_point_line_distance,
)
from .geometry_math import dot
from .suggestions import angle_claim_suggested_replacement, array_assignment_suggested_replacement


def foot_point_contract(claim: Any, facts: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    target = resolve_claim_point(facts, claim.target)
    source = resolve_claim_point(facts, claim.source)
    line = resolve_claim_pair(facts, claim.line_a)
    if not target or not source or not line:
        return None, None
    expected = fact_foot_point(facts.points[source], facts.points[line[0]], facts.points[line[1]])
    actual = facts.points[target]
    if fact_distance(actual, expected) <= 1e-3:
        return None, None
    line_no = facts.lines_by_name.get(target) or claim.line
    contract = {
        "kind": "foot_point",
        "target": target,
        "source": source,
        "line": list(line),
        "source_line": line_no,
        "expected_coords": list(expected),
        "actual_coords": list(actual),
        "claim_text": claim.claim_text,
        "suggested_replacement": array_assignment_suggested_replacement(target, expected),
        "repair_hint": f"Set {target} to the perpendicular foot from {source} to {line[0]}{line[1]}.",
        "label": f"{target} is foot of {source} to {line[0]}{line[1]}",
    }
    return contract, {**contract, "kind": "foot_point_mismatch"}


def line_intersection_contract(claim: Any, facts: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    target = resolve_claim_point(facts, claim.target)
    line_a = resolve_claim_pair(facts, claim.line_a)
    line_b = resolve_claim_pair(facts, claim.line_b)
    if not target or not line_a or not line_b:
        return None, None
    expected = fact_line_intersection(facts.points[line_a[0]], facts.points[line_a[1]], facts.points[line_b[0]], facts.points[line_b[1]])
    if expected is None:
        return None, None
    actual = facts.points[target]
    if fact_distance(actual, expected) <= 1e-3:
        return None, None
    line_no = facts.lines_by_name.get(target) or claim.line
    contract = {
        "kind": "line_intersection",
        "target": target,
        "line_a": list(line_a),
        "line_b": list(line_b),
        "source_line": line_no,
        "expected_coords": list(expected),
        "actual_coords": list(actual),
        "claim_text": claim.claim_text,
        "suggested_replacement": array_assignment_suggested_replacement(target, expected),
        "repair_hint": f"Set {target} to the intersection of {line_a[0]}{line_a[1]} and {line_b[0]}{line_b[1]}.",
        "label": f"{target} is intersection of {line_a[0]}{line_a[1]} and {line_b[0]}{line_b[1]}",
    }
    return contract, {**contract, "kind": "line_intersection_mismatch"}


def points_collinear_contract(claim: Any, facts: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    points = tuple(resolve_claim_point(facts, item) for item in claim.points)
    if len(points) != 3 or not all(points):
        return None, None
    distance = fact_point_line_distance(facts.points[points[1]], facts.points[points[0]], facts.points[points[2]])
    if distance <= 1e-3:
        return None, None
    contract = {
        "kind": "points_collinear",
        "points": list(points),
        "source_line": claim.line,
        "distance": distance,
        "claim_text": claim.claim_text,
        "repair_hint": f"Make {points[0]}, {points[1]}, {points[2]} collinear, or rewrite the false proof claim.",
        "label": f"{points[0]}, {points[1]}, {points[2]} collinear",
    }
    return contract, {**contract, "kind": "points_collinear_mismatch"}


def line_perpendicular_contract(claim: Any, facts: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    line_a = resolve_claim_pair(facts, claim.line_a)
    line_b = resolve_claim_pair(facts, claim.line_b)
    if not line_a or not line_b:
        return None, None
    dot_value = dot(facts.points[line_a[0]], facts.points[line_a[1]], facts.points[line_b[0]], facts.points[line_b[1]])
    if abs(dot_value) <= 1e-3:
        return None, None
    contract = {
        "kind": "line_perpendicular",
        "line_a": list(line_a),
        "line_b": list(line_b),
        "source_line": claim.line,
        "dot": dot_value,
        "claim_text": claim.claim_text,
        "repair_hint": f"Make {line_a[0]}{line_a[1]} perpendicular to {line_b[0]}{line_b[1]}, or rewrite the false proof claim.",
        "label": f"{line_a[0]}{line_a[1]} perpendicular to {line_b[0]}{line_b[1]}",
    }
    return contract, {**contract, "kind": "line_perpendicular_mismatch"}


def angle_equals_degrees_contract(claim: Any, facts: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    points = resolve_claim_triple(facts, claim.points)
    if not points or claim.expected_degrees is None:
        return None, None
    actual = fact_angle_degrees(facts.points[points[0]], facts.points[points[1]], facts.points[points[2]])
    if abs(actual - claim.expected_degrees) <= 1.0:
        return None, None
    contract = {
        "kind": "angle_equals_degrees",
        "points": list(points),
        "expected_degrees": claim.expected_degrees,
        "actual_degrees": actual,
        "source_line": claim.line,
        "claim_text": claim.claim_text,
        "suggested_replacement": angle_claim_suggested_replacement(claim.claim_text),
        "repair_hint": "Do not move geometry to satisfy a false proof claim; rewrite or remove the incorrect angle statement.",
        "label": f"angle {''.join(claim.points)} equals {claim.expected_degrees:g} degrees",
    }
    return contract, {**contract, "kind": "angle_claim_mismatch"}


def angle_equals_angle_contract(claim: Any, facts: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    points = resolve_claim_triple(facts, claim.points)
    reference = resolve_claim_triple(facts, claim.reference_points)
    if not points or not reference:
        return None, None
    actual = fact_angle_degrees(facts.points[points[0]], facts.points[points[1]], facts.points[points[2]])
    expected = fact_angle_degrees(facts.points[reference[0]], facts.points[reference[1]], facts.points[reference[2]])
    if abs(actual - expected) <= 1.0:
        return None, None
    contract = {
        "kind": "angle_equals_angle",
        "points": list(points),
        "reference_points": list(reference),
        "actual_degrees": actual,
        "reference_degrees": expected,
        "source_line": claim.line,
        "claim_text": claim.claim_text,
        "suggested_replacement": angle_claim_suggested_replacement(claim.claim_text),
        "repair_hint": "Rewrite the proof claim or adjust the construction so the two named angles are actually equal.",
        "label": f"angle {''.join(claim.points)} equals angle {''.join(claim.reference_points)}",
    }
    return contract, {**contract, "kind": "angle_claim_mismatch"}


def length_equals_length_contract(claim: Any, facts: Any) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    segment_a = resolve_claim_pair(facts, claim.segment_a)
    segment_b = resolve_claim_pair(facts, claim.segment_b)
    if not segment_a or not segment_b:
        return None, None
    actual = fact_distance(facts.points[segment_a[0]], facts.points[segment_a[1]])
    expected = fact_distance(facts.points[segment_b[0]], facts.points[segment_b[1]])
    if abs(actual - expected) <= 1e-3:
        return None, None
    contract = {
        "kind": "length_equals_length",
        "segment_a": list(segment_a),
        "segment_b": list(segment_b),
        "actual_length": actual,
        "reference_length": expected,
        "source_line": claim.line,
        "claim_text": claim.claim_text,
        "repair_hint": "Rewrite the length equality proof claim or adjust the construction so the two lengths are actually equal.",
        "label": f"{''.join(claim.segment_a or ())} equals {''.join(claim.segment_b or ())}",
    }
    return contract, {**contract, "kind": "length_claim_mismatch"}


def resolve_claim_point(facts: Any, name: str | None) -> str | None:
    return facts.resolve_point(name) if name else None


def resolve_claim_pair(facts: Any, pair: tuple[str, str] | None) -> tuple[str, str] | None:
    if not pair:
        return None
    resolved = tuple(resolve_claim_point(facts, item) for item in pair)
    return (resolved[0], resolved[1]) if all(resolved) else None  # type: ignore[return-value]


def resolve_claim_triple(facts: Any, triple: tuple[str, ...]) -> tuple[str, str, str] | None:
    if len(triple) != 3:
        return None
    resolved = tuple(resolve_claim_point(facts, item) for item in triple)
    return (resolved[0], resolved[1], resolved[2]) if all(resolved) else None  # type: ignore[return-value]
