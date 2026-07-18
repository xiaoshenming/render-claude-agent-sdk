"""Source-location helpers shared by geometry evidence builders."""

from __future__ import annotations

import ast

from .schemas import MAX_EXCERPT_CHARS


def source_payload(code: str, node: ast.AST, scene_id: str) -> dict[str, object]:
    lines = code.splitlines()
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", start)
    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("geometry source node requires line information")
    excerpt = "\n".join(lines[start - 1 : end]).strip()
    if len(excerpt) > MAX_EXCERPT_CHARS:
        excerpt = excerpt[: MAX_EXCERPT_CHARS - 3] + "..."
    return {
        "scene_id": scene_id,
        "line_start": start,
        "line_end": end,
        "excerpt": excerpt,
    }
