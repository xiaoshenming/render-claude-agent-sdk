from __future__ import annotations

import pytest

from manim_quality.operator.source_view import (
    SolutionSourceError,
    apply_solution_replacement,
    extract_solution,
)
from manim_quality.revisions.fingerprint import sha256_text


def test_extract_solution_returns_exact_source_lines_and_hash() -> None:
    source = (
        "# 题目头部\r\n"
        "HELPER = '保留'\r\n"
        "\r\n"
        "class Solution(BaseConfigScene):\r\n"
        "    def construct(self):\r\n"
        "        label = Text('角平分线')\r\n"
        "        self.add(label)\r\n"
        "\r\n"
        "TAIL = '也保留'\r\n"
    )
    expected = (
        "class Solution(BaseConfigScene):\r\n"
        "    def construct(self):\r\n"
        "        label = Text('角平分线')\r\n"
        "        self.add(label)"
    )

    view = extract_solution(source)

    assert view.source == expected
    assert view.start_line == 4
    assert view.end_line == 7
    assert view.sha256 == sha256_text(expected)


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("class Other(BaseConfigScene):\n    pass\n", "missing"),
        (
            "class Solution(BaseConfigScene):\n"
            "    pass\n"
            "class Solution(BaseConfigScene):\n"
            "    pass\n",
            "multiple",
        ),
        ("class Solution(Scene):\n    pass\n", "BaseConfigScene"),
        ("class Solution(BaseConfigScene)\n    pass\n", "invalid Python"),
    ],
)
def test_extract_solution_rejects_invalid_source(
    source: str,
    message: str,
) -> None:
    with pytest.raises(SolutionSourceError, match=message):
        extract_solution(source)


def test_apply_replacement_changes_only_solution_bytes() -> None:
    prefix = "# 框架头\r\nSETTING = '不能改'\r\n\r\n"
    solution = (
        "class Solution(BaseConfigScene):\r\n"
        "    def construct(self):\r\n"
        "        angle = 30\r\n"
        "        self.show(angle)"
    )
    suffix = "\r\n\r\nFOOTER = '不能改'\r\n"
    source = prefix + solution + suffix

    updated = apply_solution_replacement(
        source,
        old_text="        angle = 30\r\n        self.show(angle)",
        new_text="        angle = 45\r\n        self.show(angle)",
    )
    updated_view = extract_solution(updated)

    assert updated.encode("utf-8") == (
        prefix.encode("utf-8")
        + updated_view.source.encode("utf-8")
        + suffix.encode("utf-8")
    )
    assert updated_view.source == solution.replace("angle = 30", "angle = 45")


def test_apply_replacement_rejects_text_outside_solution() -> None:
    source = (
        "SETTING = 'outside'\n"
        "class Solution(BaseConfigScene):\n"
        "    SETTING = 'inside'\n"
    )

    with pytest.raises(SolutionSourceError, match="inside Solution"):
        apply_solution_replacement(
            source,
            old_text="SETTING = 'outside'",
            new_text="SETTING = 'changed'",
        )


def test_apply_replacement_requires_one_exact_match_inside_solution() -> None:
    source = (
        "class Solution(BaseConfigScene):\n"
        "    first = 30\n"
        "    second = 30\n"
    )

    with pytest.raises(SolutionSourceError, match="exactly once"):
        apply_solution_replacement(source, old_text="30", new_text="45")


def test_apply_replacement_rejects_invalid_result() -> None:
    source = (
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        angle = 30\n"
    )

    with pytest.raises(SolutionSourceError, match="invalid Python"):
        apply_solution_replacement(
            source,
            old_text="        angle = 30",
            new_text="    broken syntax",
        )


@pytest.mark.parametrize(
    "escaped",
    [
        "        angle = 45\nESCAPED = 99",
        "        angle = 45\nimport os",
        "        angle = 45\nclass Escaped:\n    pass",
        "        angle = 45\ndef escaped():\n    pass",
    ],
)
def test_apply_replacement_rejects_dedent_escape(escaped: str) -> None:
    source = (
        "HEADER = 'locked'\n"
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        angle = 30\n"
    )

    with pytest.raises(SolutionSourceError, match="escaped"):
        apply_solution_replacement(
            source,
            old_text="        angle = 30",
            new_text=escaped,
        )
