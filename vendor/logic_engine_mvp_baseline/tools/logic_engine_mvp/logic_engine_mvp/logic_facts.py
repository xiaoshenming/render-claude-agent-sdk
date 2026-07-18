from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass
from typing import Any


X_TOLERANCE = 1e-6
ENDPOINT_TOLERANCE = 1e-2
ANGLE_TOLERANCE_DEGREES = 0.75
POINT_PREFIXES = ("dot_", "pt_", "point_")


@dataclass(frozen=True)
class PointDef:
    var_name: str
    x: float
    y: float
    line_no: int
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class FormulaLineDef:
    var_name: str
    k: float
    b: float
    x_range: tuple[float, float]
    line_no: int
    source: str


@dataclass(frozen=True)
class VectorOffsetDef:
    var_name: str
    base_name: str
    x: float
    y: float
    z: float
    line_no: int
    source: str


@dataclass(frozen=True)
class AngleClaim:
    angle_name: str
    expected_degrees: float
    line_no: int


@dataclass(frozen=True)
class MathTexLabelDef:
    var_name: str
    value_text: str
    numeric_value: float
    class_name: str
    line_no: int
    source: str


@dataclass(frozen=True)
class ArrayPointDef:
    var_name: str
    coords: tuple[float, float, float]
    class_name: str
    line_no: int
    source: str


@dataclass(frozen=True)
class RatioPointDef:
    var_name: str
    start_name: str
    end_name: str
    ratio: float
    ratio_source: str
    class_name: str
    line_no: int
    source: str


@dataclass(frozen=True)
class DistanceLabelClaim:
    class_name: str
    points: tuple[str, str]
    claimed_length: float
    claimed_length_source: str
    line_no: int
    source: str
    literal_value: str


def extract_deterministic_logic_facts(
    code_text: str,
    *,
    sample_contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Extract high-confidence, computation-only Manim logic consistency facts."""
    try:
        tree = ast.parse(code_text)
    except SyntaxError as exc:
        return {
            "schema_version": "logic_engine_mvp.deterministic_logic_facts.v1",
            "parse_error": f"{exc.msg} at line {exc.lineno}",
            "line_endpoint_mismatch_count": 0,
            "line_endpoint_mismatches": [],
            "angle_label_mismatch_count": 0,
            "angle_label_mismatches": [],
            "arc_sweep_mismatch_count": 0,
            "arc_sweep_mismatches": [],
            "pythagorean_numeric_label_mismatch_count": 0,
            "pythagorean_numeric_label_mismatches": [],
            "distance_between_points_mismatch_count": 0,
            "distance_between_points_mismatches": [],
            "distance_label_claim_mismatch_count": 0,
            "distance_label_claim_mismatches": [],
            "midpoint_ratio_mismatch_count": 0,
            "midpoint_ratio_mismatches": [],
        }

    points, formula_lines = _extract_defs(code_text, tree)
    mismatches = _line_endpoint_mismatches(points, formula_lines)
    angle_mismatches = _angle_label_mismatches(code_text, tree)
    arc_mismatches = _arc_sweep_mismatches(code_text, tree)
    pythagorean_mismatches = _pythagorean_numeric_label_mismatches(
        code_text,
        tree,
        sample_contracts or [],
    )
    distance_mismatches = _distance_between_points_mismatches(code_text, tree, sample_contracts or [])
    distance_claim_mismatches = _distance_label_claim_mismatches(code_text, tree, sample_contracts or [])
    midpoint_mismatches = _midpoint_ratio_mismatches(code_text, tree, sample_contracts or [])
    return {
        "schema_version": "logic_engine_mvp.deterministic_logic_facts.v1",
        "line_endpoint_mismatch_count": len(mismatches),
        "line_endpoint_mismatches": mismatches,
        "angle_label_mismatch_count": len(angle_mismatches),
        "angle_label_mismatches": angle_mismatches,
        "arc_sweep_mismatch_count": len(arc_mismatches),
        "arc_sweep_mismatches": arc_mismatches,
        "pythagorean_numeric_label_mismatch_count": len(pythagorean_mismatches),
        "pythagorean_numeric_label_mismatches": pythagorean_mismatches,
        "distance_between_points_mismatch_count": len(distance_mismatches),
        "distance_between_points_mismatches": distance_mismatches,
        "distance_label_claim_mismatch_count": len(distance_claim_mismatches),
        "distance_label_claim_mismatches": distance_claim_mismatches,
        "midpoint_ratio_mismatch_count": len(midpoint_mismatches),
        "midpoint_ratio_mismatches": midpoint_mismatches,
    }


def deterministic_review_issues(review_input: dict[str, Any]) -> list[dict[str, Any]]:
    facts = review_input.get("deterministic_logic_facts") or {}
    scene_name = str((review_input.get("current_sample_evidence") or {}).get("scene_name") or "")
    issues = []
    for mismatch in facts.get("line_endpoint_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        issues.append(
            {
                "issue_type": "line_endpoint_formula_mismatch",
                "severity": "high",
                "confidence": "high",
                "evidence": (
                    f"{mismatch['line_var']} formula endpoints {mismatch['observed_endpoints']} "
                    f"do not match {'/'.join(mismatch['point_vars'])} {mismatch['intended_endpoints']}."
                ),
                "wrong_text": mismatch["exact_code_before"],
                "expected": mismatch["exact_code_after"],
                "exact_code_before": mismatch["exact_code_before"],
                "exact_code_after": mismatch["exact_code_after"],
                "needs_python_verifier": False,
                "repairability": "direct_repair",
                "source": "deterministic_logic_facts",
            }
        )
    for mismatch in facts.get("arc_sweep_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        if scene_name and mismatch.get("class_name") != scene_name:
            continue
        issues.append(
            {
                "issue_type": "angle_arc_span_wrong",
                "severity": "high",
                "confidence": "high",
                "evidence": (
                    f"{mismatch['class_name']} {mismatch['arc_var']} uses a "
                    f"{mismatch['observed_degrees']} degree sweep; the minor angle is "
                    f"{mismatch['expected_degrees']} degrees."
                ),
                "wrong_text": mismatch["exact_code_before"],
                "expected": mismatch["exact_code_after"],
                "line_replacements": mismatch["line_replacements"],
                "needs_python_verifier": False,
                "repairability": "direct_repair",
                "source": "deterministic_logic_facts",
            }
        )
    for mismatch in facts.get("angle_label_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        if scene_name and mismatch.get("class_name") != scene_name:
            continue
        issues.append(
            {
                "issue_type": "angle_label_coordinate_mismatch",
                "severity": "high",
                "confidence": "high",
                "evidence": (
                    f"{mismatch['class_name']} angle {mismatch['angle_name']} is "
                    f"{mismatch['observed_degrees']} degrees, but code labels it as "
                    f"{mismatch['expected_degrees']} degrees."
                ),
                "wrong_text": (
                    f"{mismatch['angle_name']} visual angle = {mismatch['observed_degrees']} degrees"
                ),
                "expected": f"{mismatch['angle_name']} visual angle = {mismatch['expected_degrees']} degrees",
                "line_replacements": mismatch["line_replacements"],
                "needs_python_verifier": False,
                "repairability": "direct_repair",
                "source": "deterministic_logic_facts",
            }
        )
    for mismatch in facts.get("pythagorean_numeric_label_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        if scene_name and mismatch.get("class_name") != scene_name:
            continue
        issues.append(
            {
                "issue_type": "pythagorean_numeric_label_mismatch",
                "severity": "high",
                "confidence": "high",
                "evidence": (
                    f"{'/'.join(mismatch['leg_labels'])} and {mismatch['hypotenuse_label']} "
                    f"do not satisfy a^2+b^2=c^2."
                ),
                "wrong_text": (
                    f"{mismatch['hypotenuse_label']}={mismatch['observed_values'][mismatch['hypotenuse_label']]}"
                ),
                "expected": (
                    f"{mismatch['hypotenuse_label']}={mismatch['expected_hypotenuse_label']}"
                ),
                "line_replacements": mismatch["line_replacements"],
                "needs_python_verifier": False,
                "repairability": "direct_repair",
                "source": "deterministic_logic_facts",
            }
        )
    for mismatch in facts.get("distance_between_points_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        if scene_name and mismatch.get("class_name") != scene_name:
            continue
        issues.append(
            {
                "issue_type": "distance_between_points_mismatch",
                "severity": "high",
                "confidence": "high",
                "evidence": (
                    f"{'/'.join(mismatch['points'])} length is {mismatch['observed_length']}, "
                    f"expected {mismatch['expected_length']}."
                ),
                "wrong_text": f"{mismatch['move_point']} gives length {mismatch['observed_length']}",
                "expected": f"{mismatch['move_point']} adjusted to length {mismatch['expected_length']}",
                "line_replacements": mismatch["line_replacements"],
                "needs_python_verifier": False,
                "repairability": "direct_repair",
                "source": "deterministic_logic_facts",
            }
        )
    for mismatch in facts.get("distance_label_claim_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        if scene_name and mismatch.get("class_name") != scene_name:
            continue
        points = [str(item) for item in mismatch.get("points") or []]
        point_text = "/".join(points)
        issues.append(
            {
                "issue_type": "distance_label_claim_mismatch",
                "severity": "high",
                "confidence": "high",
                "evidence": (
                    f"{point_text} displayed length is {mismatch['claimed_length']}, "
                    f"but coordinate distance is {mismatch['computed_length']}."
                ),
                "wrong_text": f"{point_text} displayed length {mismatch['claimed_length']}",
                "expected": f"{point_text} displayed length {mismatch['computed_length']}",
                "line_replacements": mismatch["line_replacements"],
                "needs_python_verifier": False,
                "repairability": "direct_repair",
                "source": "deterministic_logic_facts",
            }
        )
    for mismatch in facts.get("midpoint_ratio_mismatches") or []:
        if not isinstance(mismatch, dict):
            continue
        if scene_name and mismatch.get("class_name") != scene_name:
            continue
        issues.append(
            {
                "issue_type": "midpoint_ratio_mismatch",
                "severity": "high",
                "confidence": "high",
                "evidence": (
                    f"{mismatch['point']} uses ratio {mismatch['observed_ratio']} on "
                    f"{'/'.join(mismatch['endpoints'])}; midpoint requires 0.5."
                ),
                "wrong_text": f"{mismatch['point']} ratio {mismatch['observed_ratio']}",
                "expected": f"{mismatch['point']} ratio 0.5",
                "line_replacements": mismatch["line_replacements"],
                "needs_python_verifier": False,
                "repairability": "direct_repair",
                "source": "deterministic_logic_facts",
            }
        )
    return issues[:3]


def _pythagorean_numeric_label_mismatches(
    code_text: str,
    tree: ast.AST,
    sample_contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contracts = [
        contract
        for contract in sample_contracts
        if isinstance(contract, dict) and contract.get("kind") == "pythagorean_numeric_labels"
    ]
    if not contracts:
        return []

    labels_by_class: dict[str, dict[str, MathTexLabelDef]] = {}
    for label in sorted(_mathtex_label_defs(tree, code_text.splitlines()), key=lambda item: item.line_no):
        labels_by_class.setdefault(label.class_name, {})[label.var_name] = label

    mismatches: list[dict[str, Any]] = []
    for contract in contracts:
        leg_labels = [str(item) for item in contract.get("leg_labels") or [] if str(item).strip()]
        hypotenuse_label = str(contract.get("hypotenuse_label") or "").strip()
        if len(leg_labels) != 2 or not hypotenuse_label:
            continue
        for class_name, labels in labels_by_class.items():
            leg_a = labels.get(leg_labels[0])
            leg_b = labels.get(leg_labels[1])
            hypotenuse = labels.get(hypotenuse_label)
            if leg_a is None or leg_b is None or hypotenuse is None:
                continue
            expected_value = math.hypot(leg_a.numeric_value, leg_b.numeric_value)
            if _close(hypotenuse.numeric_value, expected_value, ENDPOINT_TOLERANCE):
                continue
            expected_label = _format_pythagorean_hypotenuse_label(leg_a.numeric_value, leg_b.numeric_value)
            exact_after = _replace_mathtex_string_literal(hypotenuse.source, expected_label)
            if exact_after is None or exact_after == hypotenuse.source:
                continue
            mismatches.append(
                {
                    "kind": "pythagorean_numeric_label_mismatch",
                    "class_name": class_name,
                    "leg_labels": leg_labels,
                    "hypotenuse_label": hypotenuse_label,
                    "observed_values": {
                        leg_a.var_name: _round(leg_a.numeric_value),
                        leg_b.var_name: _round(leg_b.numeric_value),
                        hypotenuse.var_name: _round(hypotenuse.numeric_value),
                    },
                    "expected_hypotenuse_value": _round(expected_value),
                    "expected_hypotenuse_label": expected_label,
                    "source_line": hypotenuse.line_no,
                    "line_replacements": [
                        {
                            "source_line": hypotenuse.line_no,
                            "exact_code_before": hypotenuse.source,
                            "exact_code_after": exact_after,
                        }
                    ],
                }
            )
    return mismatches


def _mathtex_label_defs(tree: ast.AST, lines: list[str]) -> list[MathTexLabelDef]:
    labels: list[MathTexLabelDef] = []
    for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        for node in ast.walk(class_node):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            call = _find_named_call(node.value, "MathTex")
            if call is None:
                continue
            value_text = _first_string_arg(call)
            numeric_value = _tex_numeric_value(value_text)
            if value_text is None or numeric_value is None:
                continue
            source = lines[node.lineno - 1].strip() if 1 <= node.lineno <= len(lines) else ""
            if not source:
                continue
            labels.append(
                MathTexLabelDef(
                    var_name=target.id,
                    value_text=value_text,
                    numeric_value=numeric_value,
                    class_name=class_node.name,
                    line_no=node.lineno,
                    source=source,
                )
            )
    return labels


def _find_named_call(node: ast.AST, name: str) -> ast.Call | None:
    if isinstance(node, ast.Call) and _call_name(node) == name:
        return node
    for child in ast.iter_child_nodes(node):
        match = _find_named_call(child, name)
        if match is not None:
            return match
    return None


def _first_string_arg(call: ast.Call) -> str | None:
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _tex_numeric_value(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    text = text.replace(" ", "").replace(",", "")
    text = text.replace("\\,", "").replace("\\;", "").replace("\\!", "")
    text = re.sub(r"\\(?:mathrm|text)\{[^{}]*\}", "", text)
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        return float(text)

    sqrt_match = re.fullmatch(
        r"(?P<coef>[-+]?\d+(?:\.\d+)?)?\\sqrt\{(?P<radicand>[-+]?\d+(?:\.\d+)?)\}",
        text,
    )
    if sqrt_match:
        coefficient = float(sqrt_match.group("coef") or 1.0)
        radicand = float(sqrt_match.group("radicand"))
        if radicand < 0:
            return None
        return coefficient * math.sqrt(radicand)

    unicode_sqrt_match = re.fullmatch(
        r"(?P<coef>[-+]?\d+(?:\.\d+)?)?√(?P<radicand>[-+]?\d+(?:\.\d+)?)",
        text,
    )
    if unicode_sqrt_match:
        coefficient = float(unicode_sqrt_match.group("coef") or 1.0)
        radicand = float(unicode_sqrt_match.group("radicand"))
        if radicand < 0:
            return None
        return coefficient * math.sqrt(radicand)

    return None


def _format_pythagorean_hypotenuse_label(leg_a: float, leg_b: float) -> str:
    expected_value = math.hypot(leg_a, leg_b)
    if _close(expected_value, round(expected_value), ENDPOINT_TOLERANCE):
        return _fmt(expected_value)
    if _close(abs(leg_a), abs(leg_b), ENDPOINT_TOLERANCE):
        coefficient = _fmt(abs(leg_a))
        return "\\sqrt{2}" if coefficient == "1" else f"{coefficient}\\sqrt{{2}}"
    return _fmt(expected_value)


def _replace_mathtex_string_literal(source: str, replacement_value: str) -> str | None:
    for quote in ('"', "'"):
        pattern = re.compile(
            rf"(?P<prefix>\bMathTex\s*\(\s*)(?P<string_prefix>[rRuU]?){re.escape(quote)}"
            rf"(?P<body>(?:\\.|[^{re.escape(quote)}\\])*){re.escape(quote)}"
        )
        match = pattern.search(source)
        if not match:
            continue
        string_prefix = match.group("string_prefix") or ""
        raw_string = "r" in string_prefix.lower()
        literal_value = replacement_value if raw_string else replacement_value.replace("\\", "\\\\")
        replacement = f"{match.group('prefix')}{string_prefix}{quote}{literal_value}{quote}"
        return source[: match.start()] + replacement + source[match.end() :]
    return None


def _distance_between_points_mismatches(
    code_text: str,
    tree: ast.AST,
    sample_contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contracts = [
        contract
        for contract in sample_contracts
        if isinstance(contract, dict) and contract.get("kind") == "distance_between_points"
    ]
    if not contracts:
        return []

    points_by_class: dict[str, dict[str, ArrayPointDef]] = {}
    for point in sorted(_array_point_defs(tree, code_text.splitlines()), key=lambda item: item.line_no):
        points_by_class.setdefault(point.class_name, {})[point.var_name] = point

    mismatches: list[dict[str, Any]] = []
    for contract in contracts:
        point_names = [str(item).strip() for item in contract.get("points") or [] if str(item).strip()]
        move_point = str(contract.get("move_point") or "").strip()
        expected_length = _contract_float(contract.get("expected_length"))
        if len(point_names) != 2 or not move_point or expected_length is None or expected_length <= 0:
            continue
        if move_point not in point_names:
            continue
        anchor_name = point_names[0] if point_names[1] == move_point else point_names[1]
        for class_name, points in points_by_class.items():
            anchor = points.get(anchor_name)
            moving = points.get(move_point)
            if anchor is None or moving is None:
                continue
            vector = tuple(moving.coords[index] - anchor.coords[index] for index in range(3))
            observed_length = math.sqrt(sum(value * value for value in vector))
            if observed_length <= X_TOLERANCE or _close(observed_length, expected_length, ENDPOINT_TOLERANCE):
                continue
            scale = expected_length / observed_length
            corrected = tuple(anchor.coords[index] + vector[index] * scale for index in range(3))
            exact_after = _replace_np_array_values(moving.source, corrected)
            if exact_after is None or exact_after == moving.source:
                continue
            mismatches.append(
                {
                    "kind": "distance_between_points_mismatch",
                    "class_name": class_name,
                    "points": point_names,
                    "move_point": move_point,
                    "anchor_point": anchor_name,
                    "observed_length": _round(observed_length),
                    "expected_length": _round(expected_length),
                    "source_line": moving.line_no,
                    "line_replacements": [
                        {
                            "source_line": moving.line_no,
                            "exact_code_before": moving.source,
                            "exact_code_after": exact_after,
                        }
                    ],
                }
            )
    return mismatches


def _distance_label_claim_mismatches(
    code_text: str,
    tree: ast.AST,
    sample_contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    coordinate_scale = _distance_label_claim_coordinate_scale(sample_contracts)
    if coordinate_scale is None:
        return []

    lines = code_text.splitlines()
    point_defs = sorted(_array_point_defs(tree, lines), key=lambda item: item.line_no)
    if not point_defs:
        return []

    point_aliases_by_class = _array_point_aliases_by_class(point_defs)
    records: list[dict[str, Any]] = []
    for claim in _distance_label_claims(tree, lines):
        aliases = point_aliases_by_class.get(claim.class_name) or {}
        point_a = _closest_array_point(aliases.get(_alias_key(claim.points[0]) or "") or [], claim.line_no)
        point_b = _closest_array_point(aliases.get(_alias_key(claim.points[1]) or "") or [], claim.line_no)
        if point_a is None or point_b is None or point_a.var_name == point_b.var_name:
            continue
        computed = math.dist(point_a.coords, point_b.coords)
        if computed <= X_TOLERANCE:
            continue
        records.append({"claim": claim, "point_a": point_a, "point_b": point_b, "coordinate_length": computed})

    mismatches: list[dict[str, Any]] = []
    for record in records:
        claim = record["claim"]
        point_a = record["point_a"]
        point_b = record["point_b"]
        computed = float(record["coordinate_length"]) * coordinate_scale
        if _close(computed, claim.claimed_length, ENDPOINT_TOLERANCE):
            continue
        exact_after = _replace_claimed_length_in_literal(
            claim.source,
            claim.literal_value,
            claim.claimed_length_source,
            _fmt_claim_length(computed),
        )
        if exact_after is None or exact_after == claim.source:
            continue
        mismatches.append(
            {
                "kind": "distance_label_claim_mismatch",
                "class_name": claim.class_name,
                "points": list(claim.points),
                "point_vars": [point_a.var_name, point_b.var_name],
                "claimed_length": _round(claim.claimed_length),
                "computed_length": _round(computed),
                "claim_line": claim.line_no,
                "line_replacements": [
                    {
                        "source_line": claim.line_no,
                        "exact_code_before": claim.source,
                        "exact_code_after": exact_after,
                    }
                ],
            }
        )
    return mismatches


def _distance_label_claim_coordinate_scale(sample_contracts: list[dict[str, Any]]) -> float | None:
    for contract in sample_contracts:
        if not isinstance(contract, dict) or contract.get("kind") != "distance_label_claims":
            continue
        scale = _contract_float(contract.get("coordinate_scale"))
        if scale is not None and scale > 0:
            return scale
    return None


def _array_point_aliases_by_class(points: list[ArrayPointDef]) -> dict[str, dict[str, list[ArrayPointDef]]]:
    by_class: dict[str, dict[str, list[ArrayPointDef]]] = {}
    for point in points:
        aliases = _point_aliases(point.var_name)
        if not aliases:
            continue
        class_aliases = by_class.setdefault(point.class_name, {})
        for alias in aliases:
            class_aliases.setdefault(_alias_key(alias), []).append(point)
    return by_class


def _closest_array_point(points: list[ArrayPointDef], claim_line: int) -> ArrayPointDef | None:
    if not points:
        return None
    return sorted(points, key=lambda item: (abs(item.line_no - claim_line), item.line_no))[0]


def _distance_label_claims(tree: ast.AST, lines: list[str]) -> list[DistanceLabelClaim]:
    claims: list[DistanceLabelClaim] = []
    seen: set[tuple[str, int, str, float]] = set()
    for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        for node in ast.walk(class_node):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            source = lines[node.lineno - 1].strip() if 1 <= node.lineno <= len(lines) else ""
            if not source:
                continue
            for parsed in _parse_distance_claim_text(node.value):
                points, claimed_length, claimed_source = parsed
                key = (class_node.name, node.lineno, "".join(points), claimed_length)
                if key in seen:
                    continue
                seen.add(key)
                claims.append(
                    DistanceLabelClaim(
                        class_name=class_node.name,
                        points=points,
                        claimed_length=claimed_length,
                        claimed_length_source=claimed_source,
                        line_no=node.lineno,
                        source=source,
                        literal_value=node.value,
                    )
                )
    return sorted(claims, key=lambda item: (item.line_no, item.points))


DISTANCE_CLAIM_RE = re.compile(
    r"(?P<segment>[A-Za-z](?:_prime|prime|'|p|′)?[A-Za-z](?:_prime|prime|'|p|′)?)"
    r"\s*(?:的?长度)?\s*(?:=|等于|为|是)\s*"
    r"(?P<length>\d+(?:\.\d+)?)"
)


def _parse_distance_claim_text(text: str) -> list[tuple[tuple[str, str], float, str]]:
    claims = []
    for match in DISTANCE_CLAIM_RE.finditer(text):
        points = _split_segment_label(match.group("segment"))
        if points is None:
            continue
        claims.append((points, float(match.group("length")), match.group("length")))
    return claims


def _split_segment_label(segment: str) -> tuple[str, str] | None:
    normalized = segment.replace("′", "'").strip()
    match = re.fullmatch(
        r"(?P<left>[A-Za-z](?:_prime|prime|'|p)?)(?P<right>[A-Za-z](?:_prime|prime|'|p)?)",
        normalized,
    )
    if not match:
        return None
    return _normalize_point_label(match.group("left")), _normalize_point_label(match.group("right"))


def _normalize_point_label(label: str) -> str:
    if label.endswith("_prime"):
        return f"{label[: -len('_prime')]}'"
    if label.endswith("prime"):
        return f"{label[: -len('prime')]}'"
    if label.endswith("p") and len(label) == 2:
        return f"{label[0]}'"
    return label


def _replace_claimed_length_in_literal(
    source: str,
    literal_value: str,
    old_value: str,
    new_value: str,
) -> str | None:
    literal_after = literal_value.replace(old_value, new_value, 1)
    if literal_after == literal_value:
        return None
    if literal_value in source:
        return source.replace(literal_value, literal_after, 1)
    return source.replace(old_value, new_value, 1) if old_value in source else None


def _fmt_claim_length(value: float) -> str:
    return _fmt_coord(value)


def _midpoint_ratio_mismatches(
    code_text: str,
    tree: ast.AST,
    sample_contracts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    contracts = [
        contract
        for contract in sample_contracts
        if isinstance(contract, dict) and contract.get("kind") == "midpoint"
    ]
    if not contracts:
        return []

    ratios_by_class: dict[str, dict[str, RatioPointDef]] = {}
    for ratio in sorted(_ratio_point_defs(tree, code_text.splitlines()), key=lambda item: item.line_no):
        ratios_by_class.setdefault(ratio.class_name, {})[ratio.var_name] = ratio

    mismatches: list[dict[str, Any]] = []
    for contract in contracts:
        point_name = str(contract.get("point") or "").strip()
        endpoints = [str(item).strip() for item in contract.get("endpoints") or [] if str(item).strip()]
        if not point_name or len(endpoints) != 2:
            continue
        endpoint_set = set(endpoints)
        for class_name, ratios in ratios_by_class.items():
            ratio = ratios.get(point_name)
            if ratio is None or {ratio.start_name, ratio.end_name} != endpoint_set:
                continue
            if _close(ratio.ratio, 0.5, X_TOLERANCE):
                continue
            exact_after = _replace_ratio_scalar(ratio.source, ratio.ratio_source, 0.5)
            if exact_after is None or exact_after == ratio.source:
                continue
            mismatches.append(
                {
                    "kind": "midpoint_ratio_mismatch",
                    "class_name": class_name,
                    "point": point_name,
                    "endpoints": endpoints,
                    "observed_ratio": _round(ratio.ratio),
                    "expected_ratio": 0.5,
                    "source_line": ratio.line_no,
                    "line_replacements": [
                        {
                            "source_line": ratio.line_no,
                            "exact_code_before": ratio.source,
                            "exact_code_after": exact_after,
                        }
                    ],
                }
            )
    return mismatches


def _array_point_defs(tree: ast.AST, lines: list[str]) -> list[ArrayPointDef]:
    points: list[ArrayPointDef] = []
    for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        for node in ast.walk(class_node):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            coords = _np_array_values(node.value)
            if coords is None or len(coords) != 3:
                continue
            source = lines[node.lineno - 1].strip() if 1 <= node.lineno <= len(lines) else ""
            if not source:
                continue
            points.append(
                ArrayPointDef(
                    var_name=target.id,
                    coords=(coords[0], coords[1], coords[2]),
                    class_name=class_node.name,
                    line_no=node.lineno,
                    source=source,
                )
            )
    return points


def _ratio_point_defs(tree: ast.AST, lines: list[str]) -> list[RatioPointDef]:
    ratios: list[RatioPointDef] = []
    for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        for node in ast.walk(class_node):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if not isinstance(target, ast.Name):
                continue
            parsed = _ratio_point_expr(node.value, lines)
            if parsed is None:
                continue
            source = lines[node.lineno - 1].strip() if 1 <= node.lineno <= len(lines) else ""
            if not source:
                continue
            start_name, end_name, ratio, ratio_source = parsed
            ratios.append(
                RatioPointDef(
                    var_name=target.id,
                    start_name=start_name,
                    end_name=end_name,
                    ratio=ratio,
                    ratio_source=ratio_source,
                    class_name=class_node.name,
                    line_no=node.lineno,
                    source=source,
                )
            )
    return ratios


def _ratio_point_expr(node: ast.AST, lines: list[str]) -> tuple[str, str, float, str] | None:
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
        return None
    if isinstance(node.left, ast.Name):
        start_name = node.left.id
        ratio_delta = _ratio_delta_expr(node.right, lines)
        if ratio_delta is not None and ratio_delta[1] == start_name:
            return start_name, ratio_delta[0], ratio_delta[2], ratio_delta[3]
    if isinstance(node.right, ast.Name):
        start_name = node.right.id
        ratio_delta = _ratio_delta_expr(node.left, lines)
        if ratio_delta is not None and ratio_delta[1] == start_name:
            return start_name, ratio_delta[0], ratio_delta[2], ratio_delta[3]
    return None


def _ratio_delta_expr(node: ast.AST, lines: list[str]) -> tuple[str, str, float, str] | None:
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mult):
        return None
    left_ratio = _numeric_value(node.left)
    right_ratio = _numeric_value(node.right)
    if left_ratio is not None:
        delta = node.right
        ratio_node = node.left
        ratio = left_ratio
    elif right_ratio is not None:
        delta = node.left
        ratio_node = node.right
        ratio = right_ratio
    else:
        return None
    if not isinstance(delta, ast.BinOp) or not isinstance(delta.op, ast.Sub):
        return None
    if not isinstance(delta.left, ast.Name) or not isinstance(delta.right, ast.Name):
        return None
    ratio_source = _node_source(lines, ratio_node)
    if not ratio_source:
        return None
    return delta.left.id, delta.right.id, ratio, ratio_source


def _node_source(lines: list[str], node: ast.AST) -> str:
    line_no = getattr(node, "lineno", 0)
    col = getattr(node, "col_offset", None)
    end_col = getattr(node, "end_col_offset", None)
    if line_no <= 0 or col is None or end_col is None or line_no > len(lines):
        return ""
    return lines[line_no - 1][col:end_col]


def _contract_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _replace_np_array_values(source: str, coords: tuple[float, float, float]) -> str | None:
    pattern = re.compile(
        r"np\.array\(\[\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d+(?:\.\d+)?\s*\]\)"
    )
    replacement = (
        f"np.array([{_fmt_coord(coords[0])}, {_fmt_coord(coords[1])}, {_fmt_coord(coords[2])}])"
    )
    return pattern.sub(replacement, source, count=1) if pattern.search(source) else None


def _replace_ratio_scalar(source: str, old_ratio_source: str, new_ratio: float) -> str | None:
    old_ratio_source = old_ratio_source.strip()
    if not old_ratio_source:
        return None
    return source.replace(old_ratio_source, _fmt_coord(new_ratio), 1)


def _arc_sweep_mismatches(code_text: str, tree: ast.AST) -> list[dict[str, Any]]:
    lines = code_text.splitlines()
    mismatches: list[dict[str, Any]] = []
    for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        construct = _construct_method(class_node)
        if construct is None:
            continue
        offsets = _vector_offsets_in_method(construct, lines)
        if not offsets:
            continue
        for arc_def in _arc_defs_in_method(construct, lines):
            mismatch = _arc_sweep_mismatch_for_def(class_node.name, arc_def, offsets)
            if mismatch is not None:
                mismatches.append(mismatch)
    return mismatches


@dataclass(frozen=True)
class ArcDef:
    var_name: str
    start_angle: str
    angle_expr: str
    line_no: int
    source: str


def _arc_defs_in_method(method: ast.FunctionDef, lines: list[str]) -> list[ArcDef]:
    defs = []
    for node in ast.walk(method):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        if not target.id.startswith("arc_") or _call_name(node.value) != "Arc":
            continue
        start_angle = _keyword_unparse(node.value, "start_angle")
        angle_expr = _keyword_unparse(node.value, "angle")
        if not start_angle or not angle_expr:
            continue
        source = lines[node.lineno - 1].strip() if 1 <= node.lineno <= len(lines) else ""
        defs.append(
            ArcDef(
                var_name=target.id,
                start_angle=start_angle,
                angle_expr=angle_expr,
                line_no=node.lineno,
                source=source,
            )
        )
    return defs


def _keyword_unparse(call: ast.Call, name: str) -> str:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.unparse(keyword.value).strip()
    return ""


def _arc_sweep_mismatch_for_def(
    class_name: str,
    arc_def: ArcDef,
    offsets: dict[str, VectorOffsetDef],
) -> dict[str, Any] | None:
    angle_name = arc_def.var_name.removeprefix("arc_")
    if len(angle_name) != 3:
        return None
    left_letter, vertex_letter, right_letter = angle_name
    expected_start = f"theta_{right_letter}"
    expected_angle = f"theta_{left_letter} - theta_{right_letter}"
    if arc_def.start_angle != expected_start or arc_def.angle_expr != expected_angle:
        return None
    left = offsets.get(f"{left_letter}_s")
    right = offsets.get(f"{right_letter}_s")
    vertex_name = f"{vertex_letter}_s"
    if left is None or right is None or left.base_name != vertex_name or right.base_name != vertex_name:
        return None
    theta_left = math.atan2(left.y, left.x)
    theta_right = math.atan2(right.y, right.x)
    observed = (theta_left - theta_right) % (2.0 * math.pi)
    if observed <= math.pi + 1e-6:
        return None
    expected = (2.0 * math.pi) - observed
    exact_after = _replace_arc_angle_expr(arc_def.source, arc_def.angle_expr)
    if exact_after is None or exact_after == arc_def.source:
        return None
    return {
        "kind": "angle_arc_span_wrong",
        "class_name": class_name,
        "arc_var": arc_def.var_name,
        "source_line": arc_def.line_no,
        "observed_degrees": _round(math.degrees(observed)),
        "expected_degrees": _round(math.degrees(expected)),
        "exact_code_before": arc_def.source,
        "exact_code_after": exact_after,
        "line_replacements": [
            {
                "source_line": arc_def.line_no,
                "exact_code_before": arc_def.source,
                "exact_code_after": exact_after,
            }
        ],
    }


def _replace_arc_angle_expr(source: str, angle_expr: str) -> str | None:
    escaped = re.escape(angle_expr).replace(r"\ ", r"\s*")
    pattern = re.compile(rf"(?P<prefix>\bangle\s*=\s*){escaped}(?=\s*[,)\n])")
    normalized = f"({angle_expr}) % TAU"
    replacement = f"min({normalized}, TAU - ({normalized}))"
    return pattern.sub(rf"\g<prefix>{replacement}", source, count=1) if pattern.search(source) else None


def _angle_label_mismatches(code_text: str, tree: ast.AST) -> list[dict[str, Any]]:
    lines = code_text.splitlines()
    mismatches: list[dict[str, Any]] = []
    for class_node in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        construct = _construct_method(class_node)
        if construct is None:
            continue
        offsets = _vector_offsets_in_method(construct, lines)
        if not offsets:
            continue
        claims = _angle_claims_in_region(lines, construct.lineno, getattr(construct, "end_lineno", construct.lineno))
        for claim in claims:
            mismatch = _angle_mismatch_for_claim(class_node.name, claim, offsets)
            if mismatch is not None:
                mismatches.append(mismatch)
    return mismatches


def _construct_method(class_node: ast.ClassDef) -> ast.FunctionDef | None:
    for item in class_node.body:
        if isinstance(item, ast.FunctionDef) and item.name == "construct":
            return item
    return None


def _vector_offsets_in_method(method: ast.FunctionDef, lines: list[str]) -> dict[str, VectorOffsetDef]:
    offsets: dict[str, VectorOffsetDef] = {}
    for node in ast.walk(method):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        offset = _vector_offset_def(target.id, node.value, node, lines)
        if offset is not None:
            offsets[offset.var_name] = offset
    return offsets


def _vector_offset_def(
    var_name: str,
    value: ast.AST,
    assign_node: ast.Assign,
    lines: list[str],
) -> VectorOffsetDef | None:
    if not isinstance(value, ast.BinOp) or not isinstance(value.op, ast.Add):
        return None
    base_name = ""
    vector_node: ast.AST | None = None
    if isinstance(value.left, ast.Name):
        base_name = value.left.id
        vector_node = value.right
    elif isinstance(value.right, ast.Name):
        base_name = value.right.id
        vector_node = value.left
    if not base_name or vector_node is None:
        return None
    values = _np_array_values(vector_node)
    if values is None or len(values) != 3:
        return None
    source = lines[assign_node.lineno - 1].strip() if 1 <= assign_node.lineno <= len(lines) else ""
    return VectorOffsetDef(
        var_name=var_name,
        base_name=base_name,
        x=values[0],
        y=values[1],
        z=values[2],
        line_no=assign_node.lineno,
        source=source,
    )


def _np_array_values(node: ast.AST) -> tuple[float, ...] | None:
    if not isinstance(node, ast.Call):
        return None
    if _call_name(node) != "array" or not node.args:
        return None
    return _numeric_sequence(node.args[0])


def _angle_claims_in_region(lines: list[str], start_line: int, end_line: int) -> list[AngleClaim]:
    claims: list[AngleClaim] = []
    seen: set[tuple[str, float]] = set()
    pattern = re.compile(r"\\angle\s*(?P<angle>[A-Za-z][A-Za-z0-9']{2,})\s*=\s*(?P<degrees>\d+(?:\.\d+)?)")
    for line_no in range(start_line, min(end_line, len(lines)) + 1):
        line = lines[line_no - 1]
        for match in pattern.finditer(line):
            angle_name = match.group("angle")
            expected = float(match.group("degrees"))
            key = (angle_name, expected)
            if key in seen:
                continue
            seen.add(key)
            claims.append(AngleClaim(angle_name=angle_name, expected_degrees=expected, line_no=line_no))
    return claims


def _angle_mismatch_for_claim(
    class_name: str,
    claim: AngleClaim,
    offsets: dict[str, VectorOffsetDef],
) -> dict[str, Any] | None:
    if len(claim.angle_name) != 3:
        return None
    left_name = f"{claim.angle_name[0]}_s"
    vertex_name = f"{claim.angle_name[1]}_s"
    right_name = f"{claim.angle_name[2]}_s"
    left = offsets.get(left_name)
    right = offsets.get(right_name)
    if left is None or right is None:
        return None
    if left.base_name != vertex_name or right.base_name != vertex_name:
        return None
    observed = _angle_degrees((left.x, left.y), (right.x, right.y))
    if observed is None or abs(observed - claim.expected_degrees) <= ANGLE_TOLERANCE_DEGREES:
        return None
    replacements = _symmetric_cross_angle_replacements(left, right, claim.expected_degrees, offsets)
    if not replacements:
        return None
    return {
        "kind": "angle_label_coordinate_mismatch",
        "class_name": class_name,
        "angle_name": claim.angle_name,
        "label_line": claim.line_no,
        "observed_degrees": _round(observed),
        "expected_degrees": _round(claim.expected_degrees),
        "line_replacements": replacements,
    }


def _angle_degrees(left: tuple[float, float], right: tuple[float, float]) -> float | None:
    left_norm = math.hypot(left[0], left[1])
    right_norm = math.hypot(right[0], right[1])
    if left_norm <= X_TOLERANCE or right_norm <= X_TOLERANCE:
        return None
    cosine = (left[0] * right[0] + left[1] * right[1]) / (left_norm * right_norm)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _symmetric_cross_angle_replacements(
    left: VectorOffsetDef,
    right: VectorOffsetDef,
    expected_degrees: float,
    offsets: dict[str, VectorOffsetDef],
) -> list[dict[str, Any]]:
    if left.base_name != right.base_name:
        return []
    if not _close(abs(left.x), abs(right.x), X_TOLERANCE) or not _close(left.y, -right.y, X_TOLERANCE):
        return []
    if abs(left.x) <= X_TOLERANCE:
        return []
    opposite_left = _opposite_offset(left, offsets)
    opposite_right = _opposite_offset(right, offsets)
    if opposite_left is None or opposite_right is None:
        return []
    target_abs_y = abs(left.x) * math.tan(math.radians(expected_degrees / 2.0))
    ordered = sorted({left, right, opposite_left, opposite_right}, key=lambda item: item.line_no)
    replacements = []
    for item in ordered:
        sign = -1.0 if item.y < 0 else 1.0
        exact_after = _replace_np_array_y(item.source, sign * target_abs_y)
        if exact_after is None or exact_after == item.source:
            return []
        replacements.append(
            {
                "source_line": item.line_no,
                "exact_code_before": item.source,
                "exact_code_after": exact_after,
            }
        )
    return replacements


def _opposite_offset(point: VectorOffsetDef, offsets: dict[str, VectorOffsetDef]) -> VectorOffsetDef | None:
    for other in offsets.values():
        if other == point or other.base_name != point.base_name:
            continue
        if _close(other.x, -point.x, X_TOLERANCE) and _close(other.y, -point.y, X_TOLERANCE):
            return other
    return None


def _replace_np_array_y(source: str, new_y: float) -> str | None:
    pattern = re.compile(
        r"np\.array\(\[\s*(?P<x>[-+]?\d+(?:\.\d+)?)\s*,\s*(?P<y>[-+]?\d+(?:\.\d+)?)\s*,\s*(?P<z>[-+]?\d+(?:\.\d+)?)\s*\]\)"
    )
    match = pattern.search(source)
    if not match:
        return None
    replacement = f"np.array([{match.group('x')}, {_fmt_coord(new_y)}, {match.group('z')}])"
    return pattern.sub(replacement, source, count=1)


def _extract_defs(code_text: str, tree: ast.AST) -> tuple[list[PointDef], list[FormulaLineDef]]:
    lines = code_text.splitlines()
    points: list[PointDef] = []
    formula_lines: list[FormulaLineDef] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or not isinstance(node.value, ast.Call):
            continue
        call_name = _call_name(node.value)
        if call_name == "make_point_by_coord":
            point = _point_def(target.id, node.value, node.lineno)
            if point is not None:
                points.append(point)
        elif call_name == "make_line_by_formula":
            line_def = _formula_line_def(target.id, node.value, node, lines)
            if line_def is not None:
                formula_lines.append(line_def)
    return points, formula_lines


def _point_def(var_name: str, call: ast.Call, line_no: int) -> PointDef | None:
    if not var_name.startswith(POINT_PREFIXES):
        return None
    x = _numeric_arg(call, 0)
    y = _numeric_arg(call, 1)
    if x is None or y is None:
        return None
    aliases = _point_aliases(var_name)
    if not aliases:
        return None
    return PointDef(var_name=var_name, x=x, y=y, line_no=line_no, aliases=aliases)


def _formula_line_def(
    var_name: str,
    call: ast.Call,
    assign_node: ast.Assign,
    lines: list[str],
) -> FormulaLineDef | None:
    if not var_name.startswith("line_"):
        return None
    if getattr(assign_node, "end_lineno", assign_node.lineno) != assign_node.lineno:
        return None
    k = _numeric_arg(call, 0)
    b = _numeric_arg(call, 1)
    x_range = _x_range(call)
    if k is None or b is None or x_range is None:
        return None
    source = lines[assign_node.lineno - 1].strip() if 1 <= assign_node.lineno <= len(lines) else ""
    if not source:
        return None
    return FormulaLineDef(var_name=var_name, k=k, b=b, x_range=x_range, line_no=assign_node.lineno, source=source)


def _line_endpoint_mismatches(points: list[PointDef], formula_lines: list[FormulaLineDef]) -> list[dict[str, Any]]:
    alias_map = _alias_map(points)
    mismatches = []
    for line_def in formula_lines:
        endpoints = _resolve_line_points(line_def.var_name, alias_map)
        if endpoints is None:
            continue
        point_a, point_b = endpoints
        if abs(point_a.x - point_b.x) <= X_TOLERANCE:
            continue
        if not _same_x_range(line_def.x_range, (point_a.x, point_b.x)):
            continue

        observed = [[_round(line_def.x_range[0]), _round(line_def.k * line_def.x_range[0] + line_def.b)]]
        observed.append([_round(line_def.x_range[1]), _round(line_def.k * line_def.x_range[1] + line_def.b)])
        intended_by_x = _intended_endpoints_for_range(line_def.x_range, point_a, point_b)
        if intended_by_x is None or _endpoints_match(observed, intended_by_x):
            continue

        correct_k = (point_b.y - point_a.y) / (point_b.x - point_a.x)
        correct_b = point_a.y - correct_k * point_a.x
        exact_after = _replace_formula_args(line_def.source, correct_k, correct_b)
        if exact_after is None or exact_after == line_def.source:
            continue
        mismatches.append(
            {
                "kind": "line_endpoint_formula_mismatch",
                "line_var": line_def.var_name,
                "source_line": line_def.line_no,
                "point_vars": [point_a.var_name, point_b.var_name],
                "observed_endpoints": observed,
                "intended_endpoints": intended_by_x,
                "correct_formula": {"k": _round(correct_k), "b": _round(correct_b)},
                "exact_code_before": line_def.source,
                "exact_code_after": exact_after,
            }
        )
    return mismatches


def _alias_map(points: list[PointDef]) -> dict[str, PointDef]:
    aliases: dict[str, PointDef] = {}
    duplicates: set[str] = set()
    for point in points:
        for alias in point.aliases:
            key = _alias_key(alias)
            if key in aliases and aliases[key] != point:
                duplicates.add(key)
                continue
            aliases[key] = point
    for key in duplicates:
        aliases.pop(key, None)
    return aliases


def _resolve_line_points(var_name: str, alias_map: dict[str, PointDef]) -> tuple[PointDef, PointDef] | None:
    raw_suffix = var_name.removeprefix("line_")
    shared_suffix_match = re.fullmatch(r"(?P<body>[A-Za-z0-9pP]+)_(?P<state>[A-Za-z0-9]+)", raw_suffix)
    if shared_suffix_match:
        shared = _resolve_shared_state_suffix(
            shared_suffix_match.group("body"),
            shared_suffix_match.group("state"),
            alias_map,
        )
        if shared is not None:
            return shared

    suffix = _alias_key(raw_suffix)
    matches: list[tuple[str, str, PointDef, PointDef]] = []
    for index in range(1, len(suffix)):
        left = suffix[:index]
        right = suffix[index:]
        point_a = alias_map.get(left)
        point_b = alias_map.get(right)
        if point_a is not None and point_b is not None and point_a != point_b:
            matches.append((left, right, point_a, point_b))
    if not matches:
        return None
    matches.sort(key=lambda item: (-(len(item[0]) + len(item[1])), -len(item[0]), item[0], item[1]))
    return matches[0][2], matches[0][3]


def _resolve_shared_state_suffix(
    body: str,
    state: str,
    alias_map: dict[str, PointDef],
) -> tuple[PointDef, PointDef] | None:
    suffix = _alias_key(body)
    matches: list[tuple[str, str, PointDef, PointDef]] = []
    for index in range(1, len(suffix)):
        left = f"{suffix[:index]}{state}"
        right = f"{suffix[index:]}{state}"
        point_a = alias_map.get(_alias_key(left))
        point_b = alias_map.get(_alias_key(right))
        if point_a is not None and point_b is not None and point_a != point_b:
            matches.append((left, right, point_a, point_b))
    if not matches:
        return None
    matches.sort(key=lambda item: (-(len(item[0]) + len(item[1])), -len(item[0]), item[0], item[1]))
    return matches[0][2], matches[0][3]


def _point_aliases(var_name: str) -> tuple[str, ...]:
    raw = ""
    for prefix in POINT_PREFIXES:
        if var_name.startswith(prefix):
            raw = var_name[len(prefix) :]
            break
    if not raw:
        return ()
    aliases = {raw, raw.replace("_", "")}
    if raw.endswith("_prime"):
        base = raw[: -len("_prime")]
        aliases.update({f"{base}p", f"{base}prime", f"{base}'", f"{base}_prime"})
    return tuple(sorted(alias for alias in aliases if alias))


def _call_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return ""


def _numeric_arg(call: ast.Call, index: int) -> float | None:
    if index >= len(call.args):
        return None
    return _numeric_value(call.args[index])


def _x_range(call: ast.Call) -> tuple[float, float] | None:
    for keyword in call.keywords:
        if keyword.arg != "x_range":
            continue
        values = _numeric_sequence(keyword.value)
        if values is not None and len(values) == 2:
            return values[0], values[1]
    if len(call.args) >= 3:
        values = _numeric_sequence(call.args[2])
        if values is not None and len(values) == 2:
            return values[0], values[1]
    return None


def _numeric_sequence(node: ast.AST) -> tuple[float, ...] | None:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    values = []
    for item in node.elts:
        value = _numeric_value(item)
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _numeric_value(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp):
        value = _numeric_value(node.operand)
        if value is None:
            return None
        if isinstance(node.op, ast.USub):
            return -value
        if isinstance(node.op, ast.UAdd):
            return value
    return None


def _same_x_range(actual: tuple[float, float], expected: tuple[float, float]) -> bool:
    return _close(actual[0], expected[0], X_TOLERANCE) and _close(actual[1], expected[1], X_TOLERANCE)


def _intended_endpoints_for_range(
    x_range: tuple[float, float],
    point_a: PointDef,
    point_b: PointDef,
) -> list[list[float]] | None:
    by_x = {round(point_a.x, 10): point_a, round(point_b.x, 10): point_b}
    intended = []
    for x_value in x_range:
        point = by_x.get(round(x_value, 10))
        if point is None:
            return None
        intended.append([_round(point.x), _round(point.y)])
    return intended


def _endpoints_match(observed: list[list[float]], intended: list[list[float]]) -> bool:
    return all(
        _close(obs[0], exp[0], X_TOLERANCE) and _close(obs[1], exp[1], ENDPOINT_TOLERANCE)
        for obs, exp in zip(observed, intended)
    )


def _replace_formula_args(source: str, k: float, b: float) -> str | None:
    pattern = re.compile(
        r"make_line_by_formula\(\s*[-+]?\d+(?:\.\d+)?\s*,\s*[-+]?\d+(?:\.\d+)?",
        flags=re.ASCII,
    )
    replacement = f"make_line_by_formula({_fmt(k)}, {_fmt(b)}"
    return pattern.sub(replacement, source, count=1) if pattern.search(source) else None


def _alias_key(value: str) -> str:
    return value.replace("_", "").strip()


def _close(left: float, right: float, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def _round(value: float) -> float:
    rounded = round(float(value), 10)
    return 0.0 if rounded == -0.0 else rounded


def _fmt(value: float) -> str:
    value = _round(value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.10g}"


def _fmt_coord(value: float) -> str:
    value = round(float(value), 6)
    if value == -0.0:
        value = 0.0
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")
