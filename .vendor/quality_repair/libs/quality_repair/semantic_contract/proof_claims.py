"""Extract compact proof claims from candidate text strings."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProofClaim:
    kind: str
    line: int
    claim_text: str
    points: tuple[str, ...] = field(default_factory=tuple)
    reference_points: tuple[str, ...] = field(default_factory=tuple)
    segment_a: tuple[str, str] | None = None
    segment_b: tuple[str, str] | None = None
    line_a: tuple[str, str] | None = None
    line_b: tuple[str, str] | None = None
    target: str | None = None
    source: str | None = None
    expected_degrees: float | None = None


def extract_proof_claims(source: str) -> list[ProofClaim]:
    claims: list[ProofClaim] = []
    seen: set[tuple[Any, ...]] = set()
    for text, line_no in _string_literals_with_lines(source):
        for claim in _angle_claims(text, line_no):
            _append_once(claims, seen, claim)
        for claim in _length_claims(text, line_no):
            _append_once(claims, seen, claim)
        for claim in _construction_claims(text, line_no):
            _append_once(claims, seen, claim)
    return claims


def _append_once(claims: list[ProofClaim], seen: set[tuple[Any, ...]], claim: ProofClaim) -> None:
    key = (
        claim.kind,
        claim.points,
        claim.reference_points,
        claim.segment_a,
        claim.segment_b,
        claim.line_a,
        claim.line_b,
        claim.target,
        claim.source,
        claim.expected_degrees,
        claim.claim_text,
    )
    if key not in seen:
        seen.add(key)
        claims.append(claim)


def _angle_claims(text: str, line_no: int) -> list[ProofClaim]:
    claims: list[ProofClaim] = []
    normalized = _normalize_latex(text)
    for segment in _claim_segments(normalized):
        angle_tokens = _angle_tokens(segment)
        degree = _degree_value(segment)
        if degree is not None and "=" in segment:
            for token in angle_tokens:
                points = _angle_token_points(token)
                if points:
                    claims.append(
                        ProofClaim(
                            kind="angle_equals_degrees",
                            line=line_no,
                            claim_text=text,
                            points=points,
                            expected_degrees=degree,
                        )
                    )
        if "=" not in segment:
            continue
        for left_token, right_token in zip(angle_tokens, angle_tokens[1:], strict=False):
            left = _angle_token_points(left_token)
            right = _angle_token_points(right_token)
            if left and right:
                claims.append(
                    ProofClaim(
                        kind="angle_equals_angle",
                        line=line_no,
                        claim_text=text,
                        points=left,
                        reference_points=right,
                    )
                )
    return claims


def _length_claims(text: str, line_no: int) -> list[ProofClaim]:
    claims: list[ProofClaim] = []
    normalized = _normalize_latex(text)
    for match in re.finditer(r"\b([A-Z]'?[A-Z]'?)\s*=\s*([A-Z]'?[A-Z]'?)\b", normalized):
        left, right = match.groups()
        if _is_sum_equation_fragment(normalized, match.start(), match.end()):
            continue
        if "∠" in normalized[max(0, match.start() - 3) : match.start() + len(left) + 1]:
            continue
        segment_a = _segment_token(left)
        segment_b = _segment_token(right)
        if segment_a and segment_b:
            claims.append(
                ProofClaim(
                    kind="length_equals_length",
                    line=line_no,
                    claim_text=text,
                    segment_a=segment_a,
                    segment_b=segment_b,
                )
            )
    return claims


def _is_sum_equation_fragment(text: str, start: int, end: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    return before in {"+", "-"} or after in {"+", "-"}


def _construction_claims(text: str, line_no: int) -> list[ProofClaim]:
    claims: list[ProofClaim] = []
    normalized = text.replace(" ", "")
    for raw_points in re.findall(r"([A-Z]'?[、,，][A-Z]'?[、,，][A-Z]'?)共线", normalized):
        points = tuple(_normalize_point_name(item) for item in re.split(r"[、,，]", raw_points))
        if len(points) == 3:
            claims.append(ProofClaim(kind="points_collinear", line=line_no, claim_text=text, points=points))
    for raw_a, raw_b in re.findall(r"([A-Z]'?[A-Z]'?)\s*(?:垂直于|⊥)\s*([A-Z]'?[A-Z]'?)", normalized):
        line_a = _segment_token(raw_a)
        line_b = _segment_token(raw_b)
        if line_a and line_b:
            claims.append(ProofClaim(kind="line_perpendicular", line=line_no, claim_text=text, line_a=line_a, line_b=line_b))
    for target, source, line in re.findall(r"([A-Z])是([A-Z]')到([A-Z]{2})的垂足", normalized):
        claims.append(
            ProofClaim(
                kind="foot_point",
                line=line_no,
                claim_text=text,
                target=target,
                source=source,
                line_a=_segment_token(line),
            )
        )
    for target, line_a, line_b in re.findall(r"([A-Z])是([A-Z]{2})与([A-Z]'?[A-Z]'?)的交点", normalized):
        claims.append(
            ProofClaim(
                kind="line_intersection",
                line=line_no,
                claim_text=text,
                target=target,
                line_a=_segment_token(line_a),
                line_b=_segment_token(line_b),
            )
        )
    return claims


def _normalize_latex(text: str) -> str:
    return (
        text.replace("\\angle", "∠")
        .replace("\\implies", "=>")
        .replace("\\therefore", "∴")
        .replace("^\\circ", "°")
        .replace("^{\\circ}", "°")
        .replace(" ", "")
    )


def _degree_value(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:°|\^\\circ|\^\{\\circ\})", text)
    return float(match.group(1)) if match else None


def _claim_segments(text: str) -> list[str]:
    return [item for item in re.split(r"[，,。；;\n]", text) if item]


def _angle_tokens(text: str) -> list[str]:
    return re.findall(r"∠\s*([A-Z](?:'|_prime)?[A-Z]?(?:'|_prime)?[A-Z]?(?:'|_prime)?)", text)


def _angle_token_points(token: str) -> tuple[str, str, str] | None:
    points = [_normalize_point_name(item) for item in re.findall(r"[A-Z](?:'|_prime)?", token)]
    if len(points) == 3:
        return (points[0], points[1], points[2])
    if len(points) == 1 and points[0] == "F":
        return ("A", "F", "E")
    return None


def _segment_token(token: str) -> tuple[str, str] | None:
    points = [_normalize_point_name(item) for item in re.findall(r"[A-Z](?:'|_prime)?", token)]
    if len(points) == 2:
        return (points[0], points[1])
    return None


def _normalize_point_name(name: str) -> str:
    return name.replace("_prime", "'")


def _string_literals_with_lines(source: str) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.STRING:
                continue
            try:
                literal = ast.literal_eval(token.string)
            except Exception:
                literal = token.string
            if isinstance(literal, str):
                pairs.append((literal, token.start[0]))
    except tokenize.TokenError:
        return pairs
    return pairs
