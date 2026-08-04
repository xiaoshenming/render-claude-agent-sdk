from pathlib import Path

from manim_quality.operator.reviewers import _content_language, _prompt


def _candidate(path: Path, language: str | None) -> Path:
    prefix = (
        f"BATCHOPS_CONTENT_LANGUAGE = {language!r}\n" if language else ""
    )
    path.write_text(
        prefix
        + "class BaseConfigScene:\n    pass\n\n"
        + "class Solution(BaseConfigScene):\n    def construct(self):\n        pass\n",
        encoding="utf-8",
    )
    return path


def test_reviewer_uses_embedded_english_language_contract(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path / "candidate.py", "en")

    assert _content_language(candidate) == "en"
    assert "expected content language is\n     `en`" in _prompt(
        "math_geometry_reviewer_v1.md", candidate, "Find x."
    )


def test_reviewer_receives_authoritative_problem_text(tmp_path: Path) -> None:
    candidate = tmp_path / "main.py"
    candidate.write_text(
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        pass\n",
        encoding="utf-8",
    )

    prompt = _prompt(
        "math_geometry_reviewer_v1.md",
        candidate,
        "作直线 DE，分别交 AC、BC 于点 F、G。",
    )

    assert "<authoritative_problem>" in prompt
    assert "作直线 DE，分别交 AC、BC 于点 F、G。" in prompt
    assert "{{PROBLEM_TEXT}}" not in prompt


def test_legacy_candidate_defaults_to_chinese(tmp_path: Path) -> None:
    assert _content_language(_candidate(tmp_path / "candidate.py", None)) == "zh-CN"
