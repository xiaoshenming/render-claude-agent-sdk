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


def test_reports_replacement_page_transition_from_helper() -> None:
    source = '''
class BaseConfigScene:
    pass
def switch_calc_stage(self, old, new):
    return ReplacementTransform(old, new)
class Solution(BaseConfigScene):
    def construct(self):
        self.play(self.switch_calc_stage(stage_a, stage_b))
'''
    value = reviewer_source_context(source)
    assert any(
        row["kind"] == "replacement_page_transition"
        for row in value["source_findings"]
    )


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
