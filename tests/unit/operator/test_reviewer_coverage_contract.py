from pathlib import Path

from manim_quality.operator.tool_schemas import FINDING_SCHEMA

PROMPTS = (
    Path(__file__).parents[3]
    / "src/manim_quality/operator/prompts"
)


def test_math_reviewer_requires_semantic_measurement_and_language_coverage():
    value = (PROMPTS / "math_geometry_reviewer_v1.md").read_text()

    for key in (
        "label_semantics",
        "geometric_measurement",
        "visible_language",
        "all_teaching_phases",
    ):
        assert key in value


def test_lifecycle_reviewer_requires_temporal_and_survival_coverage():
    value = (PROMPTS / "animation_lifecycle_reviewer_v1.md").read_text()

    for key in (
        "temporal_blank_frames",
        "content_survival",
        "ownership_closure",
        "orphan_lifecycle",
    ):
        assert key in value


def test_visual_reviewer_requires_layout_and_typography_coverage():
    value = (PROMPTS / "visual_layout_reviewer_v1.md").read_text()

    for key in (
        "typography_consistency",
        "page_grouping",
        "alignment_rhythm",
        "content_density",
        "safe_region_usage",
        "cross_page_continuity",
    ):
        assert key in value
    assert "Do not inspect video frames" in value
    assert "independent objects" in value
    assert "shared page-level" in value
    assert "A shared scale across related pages is preferred" in value
    assert "do not flag an outlier-width risk" in value
    assert "wrapper around already scattered objects" in value
    assert "is not normalized layout" in value
    assert "fixed shrink" in value
    assert "normalization_contract" in value
    assert "page_members" in value
    assert "Do not accept \"create a VGroup\" alone" in value
    assert "stack/composition helper" in value
    assert "one common fit scale" in value
    assert "make_aligned_relation_panel" in value
    assert "make_aligned_relation_stack" in value
    assert "GlobalConfig.RIGHT_X" in value
    assert "Never recommend invented board" in value
    assert "RIGHT_X` is the left boundary" in value


def test_figure_fidelity_reviewer_is_code_only_and_three_way_routed():
    value = (PROMPTS / "figure_fidelity_reviewer_v4.md").read_text()

    assert "{{FIGURE_PATH}}" in value
    assert "{{CANDIDATE_PATH}}" in value
    assert "auto_repair" in value
    assert "evidence_only" in value
    assert "human_review" in value
    assert "不读取图片、视频、帧或联系图" in value
    assert "合法替代解法" in value
    assert "确认题图与权威题目确实冲突" in value
    assert "delayed_but_present" in value
    assert "semantic_equivalence=true" in value
    assert "自动返修硬条件" in value
    assert "先记录差异，再决定动作" in value
    assert "authority_status" in value
    assert "temporal_status" in value
    assert "semantic_equivalence" in value
    assert "difference_scope" in value
    assert "runtime_problem_panel" in value
    assert "later_subquestion_stage" in value
    assert "A(2,0)、B(0,4)" in value
    assert "不审核版式美感、动画生命周期、答案泄露、教学时序" in value
    assert "不产生题图保真 issue" in value
    assert "candidate_earlier_leak" not in value
    assert "确认 figure.py 与候选都没有实际创建" in value
    assert "orientation_change" in value
    assert "心理旋转" in value
    assert "整体平移、等比例缩放" in value


def test_parent_keeps_recovery_without_dependency_bookkeeping():
    value = (PROMPTS / "quality_operator_v3.md").read_text()

    assert "best_render_passed" in value
    assert "depends_on_finding_ids" not in value
    assert "affected_symbols" not in value
    assert "root:<name>" not in value


def test_parent_requires_real_page_normalization_before_submit():
    value = (PROMPTS / "quality_operator_v3.md").read_text()

    assert "wrapping" in value
    assert "already positioned children" in value
    assert "measured bounds" in value
    assert "arbitrary fixed scale plus magic" in value
    assert "local stack/composition variant" in value
    assert "one common fit scale" in value
    assert "make_aligned_relation_stack" in value
    assert "before the first" in value
    assert "comment-only change" in value
    assert "GlobalConfig.RIGHT_X" in value
    assert "do not invent board width" in value
    assert "RIGHT_X` is the left boundary" in value
    assert "normalization_contract" in value
    assert "blocking_count` 0 only" in value


def test_coder_finding_schema_hides_audit_bookkeeping():
    properties = FINDING_SCHEMA["properties"]

    assert "depends_on_finding_ids" not in properties
    assert "affected_symbols" not in properties
    assert "source_reviewer_ids" not in properties
