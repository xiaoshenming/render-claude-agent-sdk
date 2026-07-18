"""Text/source validators for logic contracts."""

from __future__ import annotations

from typing import Any

from .math_utils import line_has_unescaped_latex_command, number, source_has_text, texts


def check_source_contains(item: dict[str, Any], source: str) -> list[dict[str, Any]]:
    expected = texts(item)
    if not expected:
        return [{"kind": "source_contains_missing_text"}]
    return [{"kind": "source_missing_text", "text": text} for text in expected if not source_has_text(source, text)]


def check_source_not_contains(item: dict[str, Any], source: str) -> list[dict[str, Any]]:
    forbidden = texts(item)
    if not forbidden:
        return [{"kind": "source_not_contains_missing_text"}]
    return [{"kind": "source_forbidden_text_present", "text": text} for text in forbidden if source_has_text(source, text)]


def check_no_unescaped_latex_command(item: dict[str, Any], source: str) -> list[dict[str, Any]]:
    target_line = number(item.get("line"))
    lines = source.splitlines()
    if target_line is not None and 1 <= int(target_line) <= len(lines):
        candidates = [(int(target_line), lines[int(target_line) - 1])]
    else:
        candidates = list(enumerate(lines, start=1))
    return [
        {"kind": "unescaped_latex_command", "line": line_no}
        for line_no, line in candidates
        if line_has_unescaped_latex_command(line)
    ]
