from __future__ import annotations

import ast
import re
from typing import Any

from .text_tools import find_matching_paren, find_source_lines, split_top_level_args


def resolve_contract_texts(code_text: str, wrong_text: str, expected_text: str) -> tuple[str, str, list[int]]:
    source_lines = find_source_lines(code_text, wrong_text)
    if source_lines:
        expanded = _expand_embedded_replacement_to_code_line(code_text, wrong_text, expected_text, source_lines)
        if expanded is not None:
            return expanded
        return wrong_text.strip(), expected_text.strip(), source_lines

    resolved = _resolve_ellipsis_call_replacement(code_text, wrong_text, expected_text)
    if resolved is not None:
        return resolved

    return wrong_text.strip(), expected_text.strip(), []


def normalize_expected_text(wrong_text: str, expected_text: str, *, code_text: str = "") -> str:
    expected_text = expected_text.strip()
    expected_text = _strip_trailing_natural_language_qualifier(expected_text)
    expected_text = _normalize_known_module_aliases(expected_text, code_text)
    formula = _extract_formula_pair(expected_text)
    if formula and "make_line_by_formula" in wrong_text:
        return _replace_make_line_formula_args(wrong_text, formula[0], formula[1])
    return expected_text


def _strip_trailing_natural_language_qualifier(text: str) -> str:
    if _is_parseable_code_line(text):
        return text
    stripped = re.sub(
        r"\s+\((?:or\s+similar|or\s+equivalent|or\s+adjust[^)]*|或者|或相近|类似)[^()]*\)\s*$",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    if stripped != text and _is_parseable_code_line(stripped):
        return stripped
    return text


def _normalize_known_module_aliases(expected_text: str, code_text: str) -> str:
    if not code_text:
        return expected_text
    if "math.sqrt(" in expected_text and _has_numpy_alias(code_text, "np") and not _has_math_import(code_text):
        return expected_text.replace("math.sqrt(", "np.sqrt(")
    return expected_text


def _has_numpy_alias(code_text: str, alias: str) -> bool:
    try:
        tree = ast.parse(code_text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name == "numpy" and (name.asname or name.name) == alias:
                    return True
    return False


def _has_math_import(code_text: str) -> bool:
    try:
        tree = ast.parse(code_text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(name.name == "math" for name in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module == "math":
            return True
    return False


def _is_parseable_code_line(text: str) -> bool:
    try:
        ast.parse(text)
    except SyntaxError:
        return False
    return True


def _expand_embedded_replacement_to_code_line(
    code_text: str,
    wrong_text: str,
    expected_text: str,
    source_lines: list[int],
) -> tuple[str, str, list[int]] | None:
    lines = code_text.splitlines()
    stripped_matches = [lines[line_no - 1].strip() for line_no in source_lines if 0 < line_no <= len(lines)]
    if not stripped_matches or len(set(stripped_matches)) != 1:
        return None
    before = stripped_matches[0]
    wrong = wrong_text.strip()
    expected = expected_text.strip()
    if before == wrong or wrong not in before:
        return None
    return before, before.replace(wrong, expected), source_lines


def _resolve_ellipsis_call_replacement(
    code_text: str,
    wrong_text: str,
    expected_text: str,
) -> tuple[str, str, list[int]] | None:
    wrong_skeleton = _parse_call_skeleton(wrong_text)
    expected_skeleton = _parse_call_skeleton(expected_text)
    if not wrong_skeleton or not expected_skeleton:
        return None
    if wrong_skeleton["target"] != expected_skeleton["target"]:
        return None
    if wrong_skeleton["callee"] != expected_skeleton["callee"]:
        return None

    matches = []
    for line_no, line in enumerate(code_text.splitlines(), start=1):
        stripped = line.strip()
        if wrong_skeleton["target"] not in stripped or f"{wrong_skeleton['callee']}(" not in stripped:
            continue
        replacement = _replace_call_prefix_args(stripped, wrong_skeleton["callee"], expected_skeleton["prefix_args"])
        if replacement:
            matches.append((line_no, stripped, replacement))

    if len(matches) != 1:
        return None
    line_no, before, after = matches[0]
    return before, after, [line_no]


def _parse_call_skeleton(text: str) -> dict[str, Any] | None:
    if "..." not in text:
        return None
    pattern = re.compile(
        r"(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<prefix>(?:self\.)?[A-Za-z_][A-Za-z0-9_\.]*)\((?P<args>.*)\)"
    )
    match = pattern.search(text.strip())
    if not match:
        return None
    args_before_ellipsis = match.group("args").split("...", 1)[0].rstrip(" ,")
    return {
        "target": match.group("target"),
        "callee": match.group("prefix").split(".")[-1],
        "prefix_args": split_top_level_args(args_before_ellipsis),
    }


def _replace_call_prefix_args(line: str, callee: str, new_prefix_args: list[str]) -> str | None:
    marker = f"{callee}("
    call_start = line.find(marker)
    if call_start < 0:
        return None
    args_start = call_start + len(marker)
    args_end = find_matching_paren(line, args_start - 1)
    if args_end is None:
        return None
    current_args = split_top_level_args(line[args_start:args_end])
    if len(current_args) < len(new_prefix_args):
        return None
    merged_args = [*new_prefix_args, *current_args[len(new_prefix_args) :]]
    return f"{line[:args_start]}{', '.join(merged_args)}{line[args_end:]}"


def _extract_formula_pair(text: str) -> tuple[str, str] | None:
    number_pair_pattern = r"\(\s*(-?(?:\d+(?:\.\d+)?|\d+\s*/\s*\d+))\s*,\s*(-?(?:\d+(?:\.\d+)?|\d+\s*/\s*\d+))\s*\)"
    formula_match = re.search(r"formula[^()]*" + number_pair_pattern, text, flags=re.IGNORECASE)
    if formula_match:
        return (_clean_number(formula_match.group(1)), _clean_number(formula_match.group(2)))

    matches = list(re.finditer(number_pair_pattern, text))
    if not matches:
        return None
    match = matches[-1]
    return (_clean_number(match.group(1)), _clean_number(match.group(2)))


def _replace_make_line_formula_args(wrong_text: str, slope: str, intercept: str) -> str:
    pattern = re.compile(r"make_line_by_formula\(\s*([^,]+)\s*,\s*([^,\)]+)\s*(?P<rest>,[^)]*)?\)")
    match = pattern.search(wrong_text)
    if not match:
        return wrong_text
    rest = match.group("rest") or ""
    replacement = f"make_line_by_formula({slope}, {intercept}{rest})"
    return wrong_text[: match.start()] + replacement + wrong_text[match.end() :]


def _clean_number(text: str) -> str:
    return re.sub(r"\s+", "", text)
