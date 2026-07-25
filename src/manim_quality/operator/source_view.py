"""AST-bound source view and exact replacements for the Solution class."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from manim_quality.revisions.fingerprint import sha256_text


class SolutionSourceError(ValueError):
    """Raised when a safe, unique Solution source view cannot be produced."""


@dataclass(frozen=True, slots=True)
class SolutionSource:
    """Exact source and identity of the single supported Solution class."""

    source: str
    start_line: int
    end_line: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _LocatedSolution:
    view: SolutionSource
    start_offset: int
    end_offset: int


def extract_solution(source: str) -> SolutionSource:
    """Extract the unique top-level ``Solution(BaseConfigScene)`` class."""

    return _locate_solution(source).view


def apply_solution_replacement(
    source: str,
    *,
    old_text: str,
    new_text: str,
) -> str:
    """Replace one exact block inside Solution while preserving outer bytes."""

    if not isinstance(old_text, str) or not old_text:
        raise SolutionSourceError("old_text must be a non-empty string")
    if not isinstance(new_text, str):
        raise SolutionSourceError("new_text must be a string")
    if old_text == new_text:
        raise SolutionSourceError("replacement must change Solution")

    located = _locate_solution(source)
    solution = located.view.source
    if solution.count(old_text) != 1:
        raise SolutionSourceError(
            "old_text must occur exactly once inside Solution"
        )

    replacement = solution.replace(old_text, new_text, 1)
    updated = (
        source[: located.start_offset]
        + replacement
        + source[located.end_offset :]
    )
    updated_location = _locate_solution(updated)
    before_prefix = source[: located.start_offset]
    before_suffix = source[located.end_offset :]
    after_prefix = updated[: updated_location.start_offset]
    after_suffix = updated[updated_location.end_offset :]
    if after_prefix != before_prefix or after_suffix != before_suffix:
        raise SolutionSourceError("replacement escaped the Solution boundary")
    return updated


def _locate_solution(source: str) -> _LocatedSolution:
    if not isinstance(source, str):
        raise TypeError("source must be str")
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        location = f"line {error.lineno}"
        if error.offset is not None:
            location += f", column {error.offset}"
        raise SolutionSourceError(
            f"invalid Python source at {location}: {error.msg}"
        ) from error

    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "Solution"
    ]
    if not candidates:
        raise SolutionSourceError("missing class Solution")
    if len(candidates) != 1:
        raise SolutionSourceError("multiple class Solution definitions")

    node = candidates[0]
    if node not in tree.body:
        raise SolutionSourceError("class Solution must be top-level")
    if not any(
        isinstance(base, ast.Name) and base.id == "BaseConfigScene"
        for base in node.bases
    ):
        raise SolutionSourceError("class Solution must inherit BaseConfigScene")
    if node.end_lineno is None:
        raise SolutionSourceError("class Solution has no complete source range")

    lines = source.splitlines(keepends=True)
    start_offset = sum(len(line) for line in lines[: node.lineno - 1])
    end_line = lines[node.end_lineno - 1]
    end_offset = (
        sum(len(line) for line in lines[: node.end_lineno - 1])
        + len(end_line.rstrip("\r\n"))
    )
    solution = source[start_offset:end_offset]
    view = SolutionSource(
        source=solution,
        start_line=node.lineno,
        end_line=node.end_lineno,
        sha256=sha256_text(solution),
    )
    return _LocatedSolution(view, start_offset, end_offset)
