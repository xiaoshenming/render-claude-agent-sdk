"""Source-text geometry contracts inferred from legacy AST evidence."""

from __future__ import annotations

import re
from typing import Any

from .ast_evidence import PointEvidence
from .geometry_math import angle_degrees, distance_tuple, point_on_line, reflect_point, segment_matches_points
from .source_utils import string_literals_with_lines
from .suggestions import (
    angle_claim_suggested_replacement,
    array_assignment_suggested_replacement,
    line_endpoint_suggested_replacement,
    point_on_line_suggested_replacement,
)


def semantic_geometry_contracts(source: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence = PointEvidence.from_source(source)
    contracts: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    _add_endpoint_contracts(evidence, contracts, findings, seen)
    _add_point_line_contracts(source, evidence, contracts, findings, seen)
    _add_reflection_contracts(source, evidence, contracts, findings, seen)
    _add_angle_measure_contracts(source, evidence, contracts, findings, seen)
    return contracts, findings


def _add_endpoint_contracts(
    evidence: PointEvidence,
    contracts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
) -> None:
    for line_name, endpoint_names in named_line_endpoint_claims(evidence):
        segment = evidence.line_segments[line_name]
        endpoint_vars = tuple(evidence.resolve_point(name) for name in endpoint_names)
        key = ("line_endpoint_match", line_name, endpoint_vars)
        if key in seen:
            continue
        seen.add(key)
        if not all(endpoint_vars):
            continue
        expected = (evidence.points[endpoint_vars[0]], evidence.points[endpoint_vars[1]])
        if segment_matches_points(segment.endpoints, expected):
            continue
        suggested = line_endpoint_suggested_replacement(line_name, expected)
        hint = f"Make {line_name} connect {endpoint_vars[0]} and {endpoint_vars[1]}; update its formula/x_range or construct it from the two points."
        contract = {
            "kind": "line_endpoint_match",
            "target": line_name,
            "endpoints": list(endpoint_vars),
            "source_line": segment.line_no,
            "expected_coords": [list(expected[0]), list(expected[1])],
            "actual_coords": [list(segment.endpoints[0]), list(segment.endpoints[1])],
            "repair_hint": hint,
            "suggested_replacement": suggested,
            "label": f"{line_name} endpoints match {endpoint_names[0]}-{endpoint_names[1]}",
        }
        contracts.append(contract)
        findings.append({**contract, "kind": "line_endpoint_mismatch"})


def _add_point_line_contracts(
    source: str,
    evidence: PointEvidence,
    contracts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
) -> None:
    for target, line, claim_line in claimed_point_lines(source):
        target_var = evidence.resolve_point(target)
        line_pair = (evidence.resolve_point(line[0]), evidence.resolve_point(line[1]))
        key = ("point_on_line", target_var, line_pair)
        if key in seen:
            continue
        seen.add(key)
        if not target_var or not all(line_pair):
            continue
        if point_on_line(evidence.points[target_var], evidence.points[line_pair[0]], evidence.points[line_pair[1]]):
            continue
        line_no = evidence.lines_by_name.get(target_var) or claim_line
        suggested = point_on_line_suggested_replacement(source, line_no, target_var)
        hint = f"Rewrite {target_var} as an affine combination of {line_pair[0]} and {line_pair[1]} with coefficients summing to 1."
        contract = {"kind": "point_on_line", "target": target_var, "line": list(line_pair), "source_line": line_no, "repair_hint": hint, "suggested_replacement": suggested, "label": f"{target} on {line}"}
        contracts.append(contract)
        findings.append({**contract, "kind": "point_not_on_claimed_line"})


def _add_reflection_contracts(
    source: str,
    evidence: PointEvidence,
    contracts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
) -> None:
    for source_point, line, reflected, claim_line in claimed_reflections(source):
        source_var = evidence.resolve_point(source_point)
        reflected_var = evidence.resolve_point(reflected)
        line_pair = (evidence.resolve_point(line[0]), evidence.resolve_point(line[1]))
        key = ("reflection_point", source_var, reflected_var, line_pair)
        if key in seen:
            continue
        seen.add(key)
        if not source_var or not reflected_var or not all(line_pair):
            continue
        expected = reflect_point(evidence.points[source_var], evidence.points[line_pair[0]], evidence.points[line_pair[1]])
        if distance_tuple(evidence.points[reflected_var], expected) <= 1e-3:
            continue
        line_no = evidence.lines_by_name.get(reflected_var) or claim_line
        suggested = array_assignment_suggested_replacement(reflected_var, expected)
        contract = {
            "kind": "reflection_point",
            "target": reflected_var,
            "source": source_var,
            "line": list(line_pair),
            "source_line": line_no,
            "expected_coords": list(expected),
            "suggested_replacement": suggested,
            "repair_hint": f"Set {reflected_var} to the expected reflected coordinates or compute it from {source_var} reflected across {line_pair[0]}{line_pair[1]}.",
            "label": f"{reflected} is reflection of {source_point} across {line}",
        }
        contracts.append(contract)
        findings.append({**contract, "kind": "reflection_point_mismatch"})


def _add_angle_measure_contracts(
    source: str,
    evidence: PointEvidence,
    contracts: list[dict[str, Any]],
    findings: list[dict[str, Any]],
    seen: set[tuple[Any, ...]],
) -> None:
    for claim in claimed_angle_measures(source):
        points = tuple(evidence.resolve_point(name) for name in claim["points"])
        if not all(points):
            continue
        key = ("angle_measure", points, claim["expected_degrees"], claim["claim_text"])
        if key in seen:
            continue
        seen.add(key)
        actual = angle_degrees(evidence.points[points[0]], evidence.points[points[1]], evidence.points[points[2]])
        if abs(actual - claim["expected_degrees"]) <= 1.0:
            continue
        suggested = angle_claim_suggested_replacement(claim["claim_text"])
        contract = {
            "kind": "angle_measure",
            "points": list(points),
            "expected_degrees": claim["expected_degrees"],
            "claim_text": claim["claim_text"],
            "source_line": claim["line"],
            "actual_degrees": actual,
            "suggested_replacement": suggested,
            "repair_hint": "Do not move geometry to satisfy a false angle claim; rewrite or remove the incorrect 90-degree claim and use a valid symmetry/equality statement.",
            "label": f"angle {''.join(claim['points'])}",
        }
        contracts.append(contract)
        findings.append({**contract, "kind": "angle_measure_mismatch"})


def named_line_endpoint_claims(evidence: PointEvidence) -> list[tuple[str, tuple[str, str]]]:
    claims: list[tuple[str, tuple[str, str]]] = []
    for line_name in evidence.line_segments:
        if line_name.startswith("line_"):
            endpoints = decode_line_suffix(line_name.removeprefix("line_"))
            if endpoints and all(evidence.resolve_point(name) for name in endpoints):
                claims.append((line_name, endpoints))
    return claims


def decode_line_suffix(suffix: str) -> tuple[str, str] | None:
    names: list[str] = []
    index = 0
    while index < len(suffix):
        char = suffix[index]
        if not char.isupper():
            return None
        name = char
        index += 1
        if index < len(suffix) and suffix[index] == "p":
            name = f"{name}_prime"
            index += 1
        elif suffix.startswith("_prime", index):
            name = f"{name}_prime"
            index += len("_prime")
        names.append(name)
    return (names[0], names[1]) if len(names) == 2 else None


def claimed_point_lines(source: str) -> list[tuple[str, str, int]]:
    claims: list[tuple[str, str, int]] = []
    for text, line_no in string_literals_with_lines(source):
        for left, right, line_left, line_right in re.findall(r"([A-Z])、([A-Z])分别是([A-Z]{2})和([A-Z]{2})上的动点", text):
            claims.append((left, line_left, line_no))
            claims.append((right, line_right, line_no))
        for point, line in re.findall(r"([A-Z])在([A-Z]{2})上", text):
            claims.append((point, line, line_no))
    return claims


def claimed_reflections(source: str) -> list[tuple[str, str, str, int]]:
    claims: list[tuple[str, str, str, int]] = []
    for text, line_no in string_literals_with_lines(source):
        for source_point, line, reflected in re.findall(r"([A-Z])\s*关于\s*([A-Z]{2})\s*的对称点\s*([A-Z]'?)", text):
            claims.append((source_point, line, reflected, line_no))
        for reflected, source_point, line in re.findall(r"([A-Z]'?)是([A-Z])关于([A-Z]{2})的对称点", text):
            claims.append((source_point, line, reflected, line_no))
    return claims


def claimed_angle_measures(source: str) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for text, line_no in string_literals_with_lines(source):
        expected = 90.0 if ("90°" in text or "九十度" in text) else None
        if expected is None:
            continue
        for token in re.findall(r"(?:∠|角\s*)([A-Z]'?[A-Z]'?[A-Z]'?)", text):
            points = re.findall(r"[A-Z]'?", token)
            if len(points) == 3:
                claims.append({"points": points, "expected_degrees": expected, "claim_text": text, "line": line_no})
    return claims
