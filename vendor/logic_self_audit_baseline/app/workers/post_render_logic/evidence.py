"""Build compact evidence for post-render logic review."""

from __future__ import annotations

import ast
import hashlib
import re
from collections.abc import Iterable
from typing import Any

from app.workers.post_render_logic.schemas import LogicEvidence, SceneDigest
from app.workers.validation import code_validator

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_MATH_SIGNAL_RE = re.compile(
    r"(\\[A-Za-z]+|[=+\-*/^_]|[<>≤≥≈≠]|°|cm|m²|m3|㎡|%|\d)"
)


def build_logic_evidence(
    *,
    code: str,
    job_id: str = "",
    problem_text: str = "",
    expected_answer: str = "",
    constraints: dict[str, Any] | None = None,
    render_meta: dict[str, Any] | None = None,
) -> LogicEvidence:
    """Create a small post-render evidence packet from runnable Manim code."""
    return LogicEvidence(
        source_code_hash=_hash_code(code),
        job_id=job_id,
        problem_text=problem_text,
        expected_answer=expected_answer,
        constraints=constraints or {},
        render_meta=render_meta or {},
        scenes=_extract_scene_digests(code),
    )


def _hash_code(code: str) -> str:
    digest = hashlib.sha256((code or "").encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _extract_scene_digests(code: str) -> list[SceneDigest]:
    digests: list[SceneDigest] = []
    for scene_id in code_validator.extract_all_scene_names(code):
        scene_code = code_validator.extract_scene_class_code(code, scene_id)
        line_start, line_end = _line_range(code, scene_code)
        strings = list(_extract_string_literals(scene_code))
        texts = _unique(s for s in strings if _CJK_RE.search(s))
        formulas = _unique(
            s for s in strings if not _CJK_RE.search(s) and _MATH_SIGNAL_RE.search(s)
        )
        digests.append(
            SceneDigest(
                scene_id=scene_id,
                line_start=line_start,
                line_end=line_end,
                texts=texts,
                formulas=formulas,
                code=scene_code,
            )
        )
    return digests


def _extract_string_literals(code: str) -> Iterable[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        yield from re.findall(r"""["']([^"']+)["']""", code or "")
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            if value:
                yield value


def _line_range(full_code: str, snippet: str) -> tuple[int, int]:
    if not snippet:
        return (0, 0)
    start = full_code.find(snippet)
    if start < 0:
        return (0, 0)
    line_start = full_code[:start].count("\n") + 1
    line_end = line_start + snippet.count("\n")
    return (line_start, line_end)


def _unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        values.append(item)
    return values
