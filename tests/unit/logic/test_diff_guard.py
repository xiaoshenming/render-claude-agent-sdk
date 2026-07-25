from manim_quality.logic._scene_evidence import extract_scenes
from manim_quality.logic.diff_guard import evaluate_logic_diff
from manim_quality.logic.repair_plan import EditRegion, RepairPlan
from manim_quality.revisions.fingerprint import code_hash

BEFORE = """from manim import *

HELPER = 12

class SceneOne(Scene):
    def construct(self):
        self.add(MathTex("x=12"))

class SceneTwo(Scene):
    def construct(self):
        self.add(Text("keep"))
"""


def plan() -> RepairPlan:
    scene = extract_scenes(BEFORE)[0]
    return RepairPlan(
        plan_id="plan-1",
        source_code_hash=code_hash(BEFORE),
        issues=(),
        target_scene_ids=("SceneOne",),
        allowed_edit_regions=(
            EditRegion("SceneOne", scene.line_start, scene.line_end),
        ),
        forbidden_changes=("unrelated Scene edits",),
        max_attempts=2,
    )


def test_diff_guard_accepts_only_declared_scene_body_change() -> None:
    after = BEFORE.replace('MathTex("x=12")', 'MathTex("x=10")')

    result = evaluate_logic_diff(BEFORE, after, plan())

    assert result.passed is True
    assert result.changed_scene_ids == ("SceneOne",)
    assert result.violations == ()
    assert result.patch_hash.startswith("sha256:")


def test_diff_guard_rejects_unrelated_top_level_or_scene_changes() -> None:
    for after, expected in (
        (BEFORE.replace("HELPER = 12", "HELPER = 10"), "outside declared Scenes"),
        (BEFORE.replace('Text("keep")', 'Text("changed")'), "SceneTwo"),
        (BEFORE.replace("SceneOne(Scene)", "SceneOne(ThreeDScene)"), "class header"),
    ):
        result = evaluate_logic_diff(BEFORE, after, plan())
        assert result.passed is False
        assert any(expected in item for item in result.violations)


def test_diff_guard_rejects_syntax_error_and_noop() -> None:
    syntax = evaluate_logic_diff(BEFORE, BEFORE + "\nif:\n", plan())
    noop = evaluate_logic_diff(BEFORE, BEFORE, plan())

    assert syntax.passed is False
    assert any("valid Python" in item for item in syntax.violations)
    assert noop.passed is False
    assert "patch made no changes" in noop.violations
