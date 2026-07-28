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


def test_parent_keeps_recovery_without_dependency_bookkeeping():
    value = (PROMPTS / "quality_operator_v3.md").read_text()

    assert "best_render_passed" in value
    assert "depends_on_finding_ids" not in value
    assert "affected_symbols" not in value
    assert "root:<name>" not in value


def test_coder_finding_schema_hides_audit_bookkeeping():
    properties = FINDING_SCHEMA["properties"]

    assert "depends_on_finding_ids" not in properties
    assert "affected_symbols" not in properties
    assert "source_reviewer_ids" not in properties
