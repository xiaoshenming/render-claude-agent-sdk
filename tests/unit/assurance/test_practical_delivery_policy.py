from pathlib import Path

from manim_quality.assurance.agent import PROMPT


def test_final_assurance_prompt_contains_practical_delivery_baseline() -> None:
    text = PROMPT.read_text(encoding="utf-8")

    assert "没有影响阅读的真实重叠" in text
    assert "示意图未严格按比例" in text
    assert "BBox=0 只能证明未检出重叠或越界" in text
    assert "不得用 BBox=0 否定" in text
    assert "旧锚点" in text
    assert "对象身份" in text
    assert "错误高亮" in text
    assert "目标转化”而不是循环论证" in text
    assert "不得再次调用 Agent" in text
    assert "数学逻辑、动画生命周期" in text
    assert "Reviewer 的原始 `needs_repair` 不是自动扣分项" in text
    assert "inspect_layout=complete" in text
    assert "必须形成至少 medium" in text
    assert "全部六个 assurance 工具" in text
    assert "七个工具" not in text
    assert "risk-frames" not in text
    assert "多模态" not in text


def test_specialist_reviewers_distinguish_schematic_and_visible_errors() -> None:
    prompts = Path(__file__).parents[3] / "src/manim_quality/operator/prompts"
    math_prompt = (prompts / "math_geometry_reviewer_v1.md").read_text(
        encoding="utf-8"
    )
    animation_prompt = (
        prompts / "animation_lifecycle_reviewer_v1.md"
    ).read_text(encoding="utf-8")
    visual_prompt = (
        prompts / "visual_layout_reviewer_v1.md"
    ).read_text(encoding="utf-8")

    assert "schematic diagram is not exactly to scale" in math_prompt
    assert "highlighted wrong segment" in math_prompt
    assert "An arrow starting from a" in math_prompt
    assert "function visualization:" in math_prompt
    assert "`kb_val` must equal `k_val * b_val`" in math_prompt
    assert "`coverage.derived_parameter_checks`" in math_prompt
    assert "`-0.6 * 0.3 = -0.18`" in math_prompt
    assert "merely possible runtime\n  symptom" in animation_prompt
    assert "Confirmed stale anchors after a fit/scale" in animation_prompt
    assert "Do not inspect video frames" in visual_prompt
    assert "do not report mathematics" in visual_prompt
    assert "page-level VGroup" in visual_prompt
    assert "wrapper around already scattered objects" in visual_prompt
    assert "not extra JSON fields" in visual_prompt


def test_assurance_uses_medium_effort_for_specialist_reviewers() -> None:
    text = (
        Path(__file__).parents[3]
        / "src/manim_quality/assurance/agent.py"
    ).read_text(encoding="utf-8")

    assert 'effort="medium"' in text
