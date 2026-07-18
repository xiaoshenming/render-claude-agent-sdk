"""AST-based compact Scene index for logic review."""

from __future__ import annotations

import ast
import re
from collections.abc import Sequence
from dataclasses import dataclass

from manim_quality.contracts._validation import require_non_empty_string

from ._errors import EvidenceBuildError

_CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_MATH = re.compile(r"(\\[A-Za-z]+|[=+\-*/^_<>≤≥≈≠]|°|%|\d)")


@dataclass(frozen=True, slots=True)
class SceneDigest:
    scene_id: str
    line_start: int
    line_end: int
    texts: Sequence[str]
    formulas: Sequence[str]

    def __post_init__(self) -> None:
        require_non_empty_string(self.scene_id, "scene_id")
        if type(self.line_start) is not int or type(self.line_end) is not int:
            raise TypeError("scene line bounds must be integers")
        if self.line_start < 1 or self.line_end < self.line_start:
            raise ValueError("scene line bounds are invalid")
        object.__setattr__(self, "texts", _unique_strings(self.texts))
        object.__setattr__(self, "formulas", _unique_strings(self.formulas))

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "scene_id": self.scene_id,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "texts": list(self.texts),
            "formulas": list(self.formulas),
        }


def extract_scenes(code: str) -> tuple[SceneDigest, ...]:
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        message = f"candidate is not valid Python: {error.msg}"
        raise EvidenceBuildError(message) from error
    scenes: list[SceneDigest] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not _declares_construct(node):
            continue
        strings = [
            item.value.strip()
            for item in ast.walk(node)
            if isinstance(item, ast.Constant)
            and isinstance(item.value, str)
            and item.value.strip()
        ]
        scenes.append(
            SceneDigest(
                scene_id=node.name,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                texts=tuple(value for value in strings if _CJK.search(value)),
                formulas=tuple(
                    value
                    for value in strings
                    if not _CJK.search(value) and _MATH.search(value)
                ),
            )
        )
    if not scenes:
        raise EvidenceBuildError("candidate Python contains no concrete Scene")
    return tuple(scenes)


def _declares_construct(node: ast.ClassDef) -> bool:
    return any(
        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == "construct"
        for item in node.body
    )


def _unique_strings(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError("scene strings must be a sequence")
    unique: list[str] = []
    for value in values:
        require_non_empty_string(value, "scene string")
        if value not in unique:
            unique.append(value)
    return tuple(unique)
