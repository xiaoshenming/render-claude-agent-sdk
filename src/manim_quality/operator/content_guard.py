"""Conservative outer checks against content-hiding logic patches."""

from __future__ import annotations

import ast

from .models import CandidateAttempt


def content_retention_reasons(
    baseline: CandidateAttempt,
    candidate: CandidateAttempt,
) -> tuple[str, ...]:
    if baseline.code_hash == candidate.code_hash:
        return ()
    try:
        before = ast.parse(baseline.code)
        after = ast.parse(candidate.code)
    except SyntaxError:
        return ("content_guard_parse_failed",)
    reasons: list[str] = []
    if not _definitions(before).issubset(_definitions(after)):
        reasons.append("top_level_content_removed")
    before_statements = _statement_count(before)
    after_statements = _statement_count(after)
    if before_statements and after_statements * 10 < before_statements * 7:
        reasons.append("excessive_ast_content_deletion")
    before_calls = _call_count(before)
    after_calls = _call_count(after)
    if before_calls and after_calls * 2 < before_calls:
        reasons.append("excessive_executable_call_deletion")
    before_lines = _nonempty_lines(baseline.code)
    after_lines = _nonempty_lines(candidate.code)
    if before_lines and after_lines * 10 < before_lines * 6:
        reasons.append("excessive_source_content_deletion")
    return tuple(reasons)


def _definitions(tree: ast.Module) -> set[tuple[str, str]]:
    return {
        (type(node).__name__, node.name)
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _statement_count(tree: ast.AST) -> int:
    return sum(isinstance(node, ast.stmt) for node in ast.walk(tree))


def _call_count(tree: ast.AST) -> int:
    return sum(isinstance(node, ast.Call) for node in ast.walk(tree))


def _nonempty_lines(code: str) -> int:
    return sum(bool(line.strip()) for line in code.splitlines())
