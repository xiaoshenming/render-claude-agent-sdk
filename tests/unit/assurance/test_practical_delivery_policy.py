from pathlib import Path

from manim_quality.assurance.agent import PROMPT


def test_final_assurance_prompt_contains_practical_delivery_baseline() -> None:
    text = PROMPT.read_text(encoding="utf-8")

    assert "没有影响阅读的真实重叠" in text
    assert "示意图未严格按比例" in text
    assert "实际视频未见异常时，不得报告为 high/blocking" in text
    assert "错误高亮" in text


def test_specialist_reviewers_distinguish_schematic_and_visible_errors() -> None:
    prompts = Path(__file__).parents[3] / "src/manim_quality/operator/prompts"
    math_prompt = (prompts / "math_geometry_reviewer_v1.md").read_text(
        encoding="utf-8"
    )
    animation_prompt = (
        prompts / "animation_lifecycle_reviewer_v1.md"
    ).read_text(encoding="utf-8")

    assert "schematic diagram is not exactly to scale" in math_prompt
    assert "highlighted wrong segment" in math_prompt
    assert "merely possible runtime\n  symptom" in animation_prompt
    assert "Confirmed stale anchors after a fit/scale" in animation_prompt
