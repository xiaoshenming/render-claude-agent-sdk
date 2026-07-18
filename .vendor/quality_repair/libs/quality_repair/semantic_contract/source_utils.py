"""Shared source-text helpers for deterministic logic contracts."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from fractions import Fraction

LATEX_COMMAND_RE = re.compile(r"\\(?:dfrac|frac|text|implies|Rightarrow|therefore|because)")
NUM_RE = r"-?(?:\d+(?:\.\d*)?|\.\d+)"


def source_line(source: str, line_no: int) -> str:
    lines = source.splitlines()
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1]
    return ""


def line_number_containing(source: str, text: str) -> int | None:
    for index, line in enumerate(source.splitlines(), start=1):
        if text in line:
            return index
    return None


def string_literals_with_lines(source: str) -> list[tuple[str, int]]:
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


def format_number(value: float) -> str:
    if abs(value) < 1e-10:
        return "0"
    limited = Fraction(value).limit_denominator(1000)
    if limited.denominator == 1:
        return str(limited.numerator)
    return f"{float(limited):.12g}"


def clean(value: float) -> float:
    if abs(value) < 1e-10:
        return 0.0
    return float(Fraction(value).limit_denominator(1000))


def string_prefix(token_text: str) -> str:
    match = re.match(r"([A-Za-z]*)['\"]", token_text)
    return match.group(1) if match else ""
