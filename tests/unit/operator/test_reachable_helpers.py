from pathlib import Path

from manim_quality.operator.native_reviewer_group import _standard_prompt
from manim_quality.operator.reachable_helpers import reviewer_source_context


def test_extracts_reachable_helper_closure_and_scale_risk() -> None:
    source = '''
class BaseConfigScene:
    def reemphasize_stroke(self, mob, scale_factor=1.03):
        return Indicate(mob, scale_factor=scale_factor)
    def highlight_equal(self, edge):
        return self.reemphasize_stroke(edge)
class Solution(BaseConfigScene):
    def construct(self):
        self.play(self.highlight_equal(edge_AB))
'''
    value = reviewer_source_context(source)
    assert [row["name"] for row in value["reachable_helpers"]] == [
        "highlight_equal", "reemphasize_stroke",
    ]
    assert any(
        row["kind"] == "transient_scale_on_original_geometry"
        for row in value["source_findings"]
    )


def test_reports_crossfade_and_opaque_semantic_anchor() -> None:
    source = '''
class BaseConfigScene:
    def write_step_row(self, row):
        return Write(row)
class Solution(BaseConfigScene):
    def construct(self):
        point_b = outline.get_points()[21]
        self.play_steps_evenly([
            FadeOut(old_page), self.write_step_row(new_row)
        ], tracker)
'''
    value = reviewer_source_context(source)
    kinds = {row["kind"] for row in value["source_findings"]}
    assert "opaque_semantic_point_index" in kinds
    assert "crossfade_page_ownership" in kinds


def test_reports_duplicate_reveal_without_retire() -> None:
    source = '''
class BaseConfigScene:
    pass
class Solution(BaseConfigScene):
    def construct(self):
        self.play(FadeIn(arc_EFC))
        self.play(FadeIn(arc_EFC))
'''
    value = reviewer_source_context(source)
    assert any(
        row["kind"] == "duplicate_reveal_without_retire"
        and "arc_EFC" in row["evidence"]
        for row in value["source_findings"]
    )


def test_reports_duplicate_retire_without_reveal() -> None:
    source = '''
class BaseConfigScene:
    pass
class Solution(BaseConfigScene):
    def construct(self):
        self.play(FadeOut(panel_2_proof))
        self.play(FadeOut(panel_2_proof))
'''
    value = reviewer_source_context(source)
    assert any(
        row["kind"] == "duplicate_retire_without_reveal"
        and "panel_2_proof" in row["evidence"]
        for row in value["source_findings"]
    )


def test_reports_unretired_stage_and_ignores_normal_switch() -> None:
    source = '''
class BaseConfigScene:
    pass
class Solution(BaseConfigScene):
    def construct(self):
        self.play(stage_a.show())
        self.play(stage_b.show())
        self.play(self.switch_calc_stage(stage_b, stage_c))
'''
    value = reviewer_source_context(source)
    rows = [row for row in value["source_findings"]
            if row["kind"] == "stage_owner_not_retired"]
    assert [(row["old_stage"], row["new_stage"]) for row in rows] == [
        ("stage_a", "stage_b")]


def test_reports_anisotropic_perpendicularity() -> None:
    source = r'''
class GlobalConfig:
    AXIS_BOX_X_RANGE = (-6.25, -0.45)
    AXIS_BOX_Y_RANGE = (-3.05, 1.92)
class BaseConfigScene:
    pass
class Solution(BaseConfigScene):
    def construct(self):
        axes = self.make_axes_manual(x_range=[-4, 2], y_range=[-1, 5])
        line_AB = self.make_line_by_formula(1, 3)
        line_PQ = self.make_line_by_formula(-1, 0)
        note = r"PQ \perp AB"
'''
    value = reviewer_source_context(source)
    rows = [row for row in value["source_findings"]
            if row["kind"] == "anisotropic_perpendicularity"]
    assert len(rows) == 1
    assert rows[0]["deviation_degrees"] > 2


def test_reviewer_prompt_receives_deterministic_findings(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text('''
class BaseConfigScene:
    pass
class Solution(BaseConfigScene):
    def construct(self):
        point_b = outline.get_points()[21]
''')
    prompt = _standard_prompt(
        "math_geometry_reviewer_v1.md", candidate, "题目", "脚本",
        parsed_answer="答案",
    )
    assert "<deterministic_source_findings>" in prompt
    assert "opaque_semantic_point_index" in prompt
