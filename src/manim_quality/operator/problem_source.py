"""Minimal deterministic extraction of the locked problem source."""

from __future__ import annotations

import ast


def extract_problem_text(candidate_code: str) -> str:
    if not isinstance(candidate_code, str) or not candidate_code.strip():
        raise ValueError("candidate code must be non-empty")
    try:
        tree = ast.parse(candidate_code)
    except SyntaxError as error:
        raise ValueError(
            "candidate code must parse before problem extraction"
        ) from error
    docstring = ast.get_docstring(tree, clean=False)
    if isinstance(docstring, str) and docstring.strip():
        return docstring.strip()
    comments: list[str] = []
    for line in candidate_code.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            comments.append(stripped[1:].strip())
            continue
        if not stripped and comments:
            continue
        if stripped:
            break
    text = "\n".join(item for item in comments if item).strip()
    if not text:
        raise ValueError(
            "candidate has no module docstring or leading problem comments"
        )
    return text
