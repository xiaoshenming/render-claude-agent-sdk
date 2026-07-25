from __future__ import annotations

import ast
import re
from typing import Any

from .text_tools import (
    find_exact_code_line_numbers,
    find_matching_paren,
    line_has_kwarg_value,
    nonempty_stripped_lines,
    replace_kwarg_value,
    split_top_level_args,
)


ExpandedContract = tuple[str, str, str, list[int]]


def expand_structured_issue(index: int, issue: dict[str, Any], code_text: str) -> list[ExpandedContract]:
    wrong_text = str(issue.get("exact_code_before") or issue.get("wrong_text") or issue.get("wrong_claim") or "")
    expected_text = str(issue.get("exact_code_after") or issue.get("expected") or issue.get("expected_text") or "")
    base_id = str(issue.get("issue_id") or f"issue-{index:03d}")
    for expander in (
        _expand_multiline_exact_replacement_issue,
        _expand_angle_mark_order_issue,
        _expand_exact_arc_block_replacement_issue,
        _expand_arc_positive_sweep_issue,
        _expand_parameter_replacement_issue,
    ):
        expanded = expander(base_id, wrong_text, expected_text, code_text)
        if expanded:
            return expanded
    return []


def _expand_multiline_exact_replacement_issue(
    base_id: str,
    wrong_text: str,
    expected_text: str,
    code_text: str,
) -> list[ExpandedContract]:
    wrong_lines = nonempty_stripped_lines(wrong_text)
    expected_lines = nonempty_stripped_lines(expected_text)
    if len(wrong_lines) <= 1 or len(wrong_lines) != len(expected_lines):
        return []

    code_lines = code_text.splitlines()
    expanded: list[ExpandedContract] = []
    for index, (wrong_line, expected_line) in enumerate(zip(wrong_lines, expected_lines), start=1):
        if wrong_line == expected_line:
            continue
        source_lines = find_exact_code_line_numbers(code_lines, wrong_line)
        if not source_lines:
            return []
        expanded.append((f"{base_id}-line-{index}", wrong_line, expected_line, source_lines))
    return expanded


def _expand_exact_arc_block_replacement_issue(
    base_id: str,
    wrong_text: str,
    expected_text: str,
    code_text: str,
) -> list[ExpandedContract]:
    wrong_lines = nonempty_stripped_lines(wrong_text)
    if len(wrong_lines) != 1:
        return []
    wrong_line = wrong_lines[0]
    skeleton = _parse_arc_angle_skeleton(wrong_line)
    if not skeleton:
        return []

    expected_lines = _split_semicolon_code_statements(expected_text)
    if len(expected_lines) <= 1:
        return []
    expected_arc_line = _expected_arc_line_for_target(expected_lines, skeleton["target"])
    if expected_arc_line is None:
        return []
    if _parse_arc_angle_skeleton(expected_arc_line) is None:
        return []

    expected_block = "\n".join(expected_lines)
    try:
        ast.parse(expected_block)
    except SyntaxError:
        return []

    source_lines = find_exact_code_line_numbers(code_text.splitlines(), wrong_line)
    if not source_lines:
        return []
    return [(f"{base_id}-arc-block", wrong_line, expected_block, source_lines)]


def _split_semicolon_code_statements(text: str) -> list[str]:
    return [part.strip() for part in text.split(";") if part.strip()]


def _expected_arc_line_for_target(lines: list[str], target: str) -> str | None:
    prefix = f"{target} = "
    for line in lines:
        if line.startswith(prefix) and "Arc(" in line:
            return line
    return None


def _expand_angle_mark_order_issue(
    base_id: str,
    wrong_text: str,
    expected_text: str,
    code_text: str,
) -> list[ExpandedContract]:
    expected_pairs = _parse_angle_mark_expected_pairs(expected_text)
    if not expected_pairs:
        return []
    lines = code_text.splitlines()
    expanded: list[ExpandedContract] = []
    for target, (p1, p2) in expected_pairs.items():
        matches = []
        for line_no, line in enumerate(lines, start=1):
            stripped = line.strip()
            if target not in stripped or "make_angle_mark(" not in stripped:
                continue
            replacement = _replace_make_angle_mark_points(stripped, p1, p2)
            if replacement and replacement != stripped:
                matches.append((line_no, stripped, replacement))
        for match_index, (line_no, before, after) in enumerate(matches, start=1):
            expanded.append((f"{base_id}-angle-{target}-{match_index}", before, after, [line_no]))
    return expanded


def _parse_angle_mark_expected_pairs(text: str) -> dict[str, tuple[str, str]]:
    pairs: dict[str, tuple[str, str]] = {}
    pattern = re.compile(
        r"(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*p1\s*=\s*(?P<p1>[^,;]+)\s*,\s*p2\s*=\s*(?P<p2>[^;]+)"
    )
    for match in pattern.finditer(text):
        pairs[match.group("target")] = (match.group("p1").strip(), match.group("p2").strip())
    return pairs


def _replace_make_angle_mark_points(line: str, p1: str, p2: str) -> str | None:
    marker = "make_angle_mark("
    call_start = line.find(marker)
    if call_start < 0:
        return None
    args_start = call_start + len(marker)
    args_end = find_matching_paren(line, args_start - 1)
    if args_end is None:
        return None
    current_args = split_top_level_args(line[args_start:args_end])
    if len(current_args) < 3:
        return None
    merged_args = [current_args[0], p1, p2, *current_args[3:]]
    return f"{line[:args_start]}{', '.join(merged_args)}{line[args_end:]}"


def _expand_arc_positive_sweep_issue(
    base_id: str,
    wrong_text: str,
    expected_text: str,
    code_text: str,
) -> list[ExpandedContract]:
    skeleton = _parse_arc_angle_skeleton(wrong_text)
    expected_angle = _extract_expected_angle_expression(expected_text)
    if not skeleton or not expected_angle:
        return []
    expanded = []
    for line_no, line in enumerate(code_text.splitlines(), start=1):
        stripped = line.strip()
        if not _line_matches_arc_skeleton(stripped, skeleton):
            continue
        replacement = replace_kwarg_value(stripped, "angle", skeleton["angle"], expected_angle)
        if replacement and replacement != stripped:
            expanded.append((f"{base_id}-arc-{line_no}", stripped, replacement, [line_no]))
    return expanded


def _parse_arc_angle_skeleton(text: str) -> dict[str, str] | None:
    if "Arc(" not in text:
        return None
    match = re.search(
        r"(?P<target>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*Arc\(.*?start_angle\s*=\s*(?P<start>[^,]+),\s*angle\s*=\s*(?P<angle>[^,\)]+)",
        text,
    )
    if not match:
        return None
    return {
        "target": match.group("target").strip(),
        "start_angle": match.group("start").strip(),
        "angle": match.group("angle").strip(),
    }


def _extract_expected_angle_expression(text: str) -> str | None:
    match = re.search(r"(?<![A-Za-z0-9_])angle\s*=\s*(?P<angle>.+?)(?:\s+if\b|[,.;]|$)", text)
    if not match:
        return None
    return match.group("angle").strip()


def _line_matches_arc_skeleton(line: str, skeleton: dict[str, str]) -> bool:
    if skeleton["target"] not in line or "Arc(" not in line:
        return False
    return line_has_kwarg_value(line, "start_angle", skeleton["start_angle"]) and line_has_kwarg_value(
        line, "angle", skeleton["angle"]
    )


def _expand_parameter_replacement_issue(
    base_id: str,
    wrong_text: str,
    expected_text: str,
    code_text: str,
) -> list[ExpandedContract]:
    parsed = _parse_targeted_parameter_replacement(wrong_text, expected_text)
    if not parsed:
        return []
    param, old_value, new_value, targets = parsed
    lines = code_text.splitlines()
    expanded = []
    for target in targets:
        for line_no, line in _target_assignment_region(lines, target):
            stripped = line.strip()
            if not line_has_kwarg_value(stripped, param, old_value):
                continue
            replacement = replace_kwarg_value(stripped, param, old_value, new_value)
            if replacement and replacement != stripped:
                expanded.append((f"{base_id}-param-{target}-{line_no}", stripped, replacement, [line_no]))
    return expanded


def _parse_targeted_parameter_replacement(
    wrong_text: str,
    expected_text: str,
) -> tuple[str, str, str, list[str]] | None:
    wrong = re.search(r"(?P<param>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<old>.+?)\s+in\s+(?P<targets>.+)$", wrong_text)
    expected = re.search(r"(?P<param>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<new>.+)$", expected_text)
    if not wrong or not expected or wrong.group("param") != expected.group("param"):
        return None
    targets = [part.strip() for part in re.split(r"\band\b|,", wrong.group("targets")) if part.strip()]
    return (wrong.group("param").strip(), wrong.group("old").strip(), expected.group("new").strip(), targets)


def _target_assignment_region(lines: list[str], target: str) -> list[tuple[int, str]]:
    start_index = None
    for index, line in enumerate(lines):
        if re.match(rf"\s*{re.escape(target)}\s*=", line):
            start_index = index
            break
    if start_index is None:
        return []
    region: list[tuple[int, str]] = []
    depth = 0
    seen_paren = False
    for index in range(start_index, len(lines)):
        line = lines[index]
        region.append((index + 1, line))
        depth += line.count("(") - line.count(")")
        seen_paren = seen_paren or "(" in line
        if index > start_index and (not seen_paren or depth <= 0):
            break
    return region
