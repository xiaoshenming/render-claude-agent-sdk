from __future__ import annotations

import json
from pathlib import Path

from libs.quality_repair.deterministic_layout import apply_layout_prepatch


def _write_brief(workdir: Path, failure_type: str, *, confidence: float = 0.94) -> None:
    (workdir / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "schema_version": "quality_repair.layout_repair_brief.v1",
                "blocking_count": 8,
                "summary": {
                    "primary_failure_type": failure_type,
                    "primary_confidence": confidence,
                },
                "clusters": [
                    {
                        "cluster_id": "C01",
                        "priority": 1,
                        "failure_type": failure_type,
                        "confidence": confidence,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_label_shape_overlap_patches_point_label_helper(tmp_path: Path) -> None:
    _write_brief(tmp_path, "label_shape_overlap")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def avoid_overlap(self, label, anchor, obstacles=None, directions=None, buff=0.1):
        return label

    def make_point_label(self, text, dot_or_point, direction=UR, color=None, obstacles=None):
        label = self.make_label_text(text, color=color)
        anchor = dot_or_point
        directions = [direction, UL, UR, DL, DR, UP, DOWN, LEFT, RIGHT]
        return self.avoid_overlap(label, anchor, obstacles=obstacles, directions=directions, buff=0.12)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "label_shape_overlap_helper_buff" in report.patch_names
    assert "make_point_label_radial_direction" in report.patch_names
    assert "buff=0.25" in patched
    assert "buff=label_buff" in patched
    assert 'origin = getattr(self, "_axis_origin", ORIGIN)' in patched
    assert "axis_directions.extend([UR, DR, UP, DOWN, UL, DL])" in patched
    assert "axis_directions.extend([UL, UR, LEFT, RIGHT, DL, DR])" in patched
    assert "if axis_directions:" in patched
    assert "directions = axis_directions + [direction, preferred_direction]" in patched
    assert "elif numbered_label:" in patched
    assert "directions = [direction]" in patched
    assert "coordinate_label = True" in patched
    assert "and not coordinate_label" in patched
    assert "label_buff = 1.15 if numbered_label else 0.75 if coordinate_label else 0.45" in patched
    assert "placed = self.avoid_overlap" in patched
    assert "placed.get_left()[0] < -6.35" in patched


def test_label_shape_overlap_replaces_avoid_overlap_with_safe_geometry_scoring(tmp_path: Path) -> None:
    _write_brief(tmp_path, "label_shape_overlap")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def avoid_overlap(self, label, anchor, obstacles=None, directions=None, buff=0.1):
        obstacles = list(obstacles or [])
        directions = directions or [UR, UL, DR, DL, UP, DOWN, RIGHT, LEFT]
        best = None
        best_score = -10**9
        for direction in directions:
            candidate = label.copy()
            candidate.next_to(anchor, direction, buff=buff)
            penalty = 0
            for obstacle in obstacles:
                if candidate.get_right()[0] > obstacle.get_left()[0]:
                    penalty += 100
            best = candidate
        label.move_to(best.get_center())
        return label

    def make_point_label(self, text, dot_or_point, direction=UR, color=None, obstacles=None):
        return label
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "label_avoid_overlap_geometry" in report.patch_names
    assert 'if item.__class__.__name__ in {"Line", "Arrow"}:' in patched
    assert "obs.get_num_points() <= 0" in patched
    assert "def line_close(cand, obs):" in patched
    assert "def segments_intersect" in patched
    assert "rect_edges(cand)" in patched
    assert "dict.fromkeys" not in patched
    assert "np.allclose(item, existing)" in patched
    assert "base_directions + [LEFT" not in patched


def test_label_shape_overlap_uses_brief_evidence_to_patch_label_callsite_direction(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "label_shape_overlap",
                        "confidence": 0.92,
                        "evidence": [
                            {
                                "category": "label_shape_overlap_risk",
                                "objects": [
                                    {"class": "MathTex", "text": "A(-3,0)", "center": [-4.7, -1.7]},
                                    {"class": "Line", "center": [-4.1, -0.4]},
                                ],
                            },
                            {
                                "category": "label_shape_overlap_risk",
                                "objects": [
                                    {"class": "Text", "text": "P", "center": [2.9, 1.6]},
                                    {"class": "Circle", "center": [2.1, 0.9]},
                                ],
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        label_a = self.make_point_label("A(-3,0)", dot_a, direction=DOWN, obstacles=[axes, line_ab])
        label_p = self.make_unknown_point_label("P", dot_p, direction=UP, obstacles=[circle])
        self.reveal_point_coord(label_q, "A(-3,0)", direction=RIGHT)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "point_label_callsite_directions" in report.patch_names
    assert 'self.make_point_label("A(-3,0)", dot_a, direction=DL, obstacles=[axes, line_ab])' in patched
    assert 'self.make_unknown_point_label("P", dot_p, direction=UR, obstacles=[circle])' in patched
    assert 'self.reveal_point_coord(label_q, "A(-3,0)", direction=DL)' in patched


def test_label_shape_overlap_patches_direct_text_label_direction(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "label_shape_overlap",
                        "confidence": 0.91,
                        "evidence": [
                            {
                                "category": "label_shape_overlap_risk",
                                "objects": [
                                    {"class": "Text", "text": "Q", "center": [-1.89, -0.86]},
                                    {"class": "Line", "center": [-2.14, -1.2]},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        lbl_Q = Text("Q", font_size=16, color=TEXT_COLOR).next_to(Q, UR, buff=0.05)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "label_shape_direct_text_label_directions" in report.patch_names
    assert 'lbl_Q = Text("Q", font_size=16, color=TEXT_COLOR).next_to(Q, UR, buff=0.55)' in patched


def test_label_shape_overlap_adds_existing_geometry_to_label_obstacles(tmp_path: Path) -> None:
    _write_brief(tmp_path, "label_shape_overlap")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        axes = self.make_axes_manual()
        line_ac = self.make_line_by_formula(1, 3)
        area_abc = self.make_area_by_coords([(-3, 0), (3, 0), (0, 3)])
        dot_a = self.make_point_by_coord(-3, 0)
        label_a = self.make_point_label("A(-3,0)", dot_a, direction=DOWN, obstacles=[axes])
        label_p = self.make_unknown_point_label("P", dot_p, direction=UR, obstacles=[axes, line_ac])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "label_obstacles_from_existing_geometry" in report.patch_names
    assert 'self.make_point_label("A(-3,0)", dot_a, direction=DOWN, obstacles=[axes, line_ac, area_abc])' in patched
    assert 'self.make_unknown_point_label("P", dot_p, direction=UR, obstacles=[axes, line_ac, area_abc])' in patched


def test_label_shape_overlap_adds_existing_label_obstacles_for_numbered_points(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "label_shape_overlap",
                        "confidence": 0.91,
                        "evidence": [
                            {
                                "category": "label_shape_overlap_risk",
                                "objects": [
                                    {"class": "Text", "text": "P₁", "center": [-2.5, 0.9]},
                                    {"class": "Line", "center": [-2.6, -0.2]},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        axes = self.make_axes_manual()
        lbl_A = self.make_unknown_point_label("A", dot_A, direction=UR, obstacles=[axes])
        lbl_P1 = self.make_unknown_point_label("P_1", dot_P1, direction=UL, obstacles=[axes])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "label_obstacles_from_existing_labels" in report.patch_names
    assert 'lbl_P1 = self.make_unknown_point_label("P_1", dot_P1, direction=UL, obstacles=[axes, lbl_A])' in patched


def test_formula_stack_pressure_fades_right_panel_formulas_before_next_heading(tmp_path: Path) -> None:
    _write_brief(tmp_path, "generic_layout_overlap")
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.91,
                        "evidence": [
                            {
                                "category": "text_formula_overlap",
                                "objects": [
                                    {"class": "MathTex", "text": "AB = 2"},
                                    {"class": "Text", "text": "大三角形 PAB 的面积："},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        step_panel_1 = self.make_step_panel(["交点", "P 坐标"])
        eq_sys = self.make_formula(r"system")
        eq_sys.next_to(step_panel_1[1] if len(step_panel_1) > 1 else step_panel_1[-1], DOWN, aligned_edge=LEFT)
        self.play_steps_evenly([FadeIn(eq_sys)], tracker)
        eq_x = self.make_formula(r"x = 1")
        eq_x.next_to(eq_sys, DOWN, aligned_edge=LEFT)
        self.play_steps_evenly([FadeIn(eq_x)], tracker)
        step_panel_2 = self.make_step_panel(["割补", "底边", "大三角形 PAB 的面积：", "小三角形 CAB 的面积："])
        eq_ab = self.make_formula(r"AB = 2")
        eq_ab.next_to(step_panel_2[1] if len(step_panel_2) > 1 else step_panel_2[-1], DOWN, aligned_edge=LEFT)
        self.play_steps_evenly([FadeIn(eq_ab)], tracker)
        self.play_steps_evenly([FadeIn(area_PAB), Write(step_panel_2[2] if len(step_panel_2) > 2 else step_panel_2[-1])], tracker)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "right_panel_formula_lifecycle" in report.patch_names
    assert "eq_x.next_to(step_panel_1[1] if len(step_panel_1) > 1 else step_panel_1[-1], DOWN, aligned_edge=LEFT)" in patched
    assert "self.play_steps_evenly([FadeOut(eq_sys), FadeIn(eq_x)], tracker)" in patched
    assert "self.play_steps_evenly([FadeOut(eq_ab), FadeIn(area_PAB), Write(step_panel_2[2] if len(step_panel_2) > 2 else step_panel_2[-1])], tracker)" in patched


def test_formula_stack_pressure_patches_option_analysis_table_spacing(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.91,
                        "evidence": [
                            {
                                "category": "text_formula_overlap",
                                "objects": [
                                    {"class": "MathTex", "text": "x^2-1 < 0"},
                                    {"class": "MathTex", "text": "\\text{不符合}"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        col1_x = -5.5
        col2_x = -3.5
        col3_x = -0.8
        a_det = MathTex(r"long", color=TEXT_COLOR).scale(0.7).move_to([col2_x, 1, 0], aligned_edge=LEFT)
        a_res = MathTex(r"\\text{不符合}", color=RED).scale(0.8).move_to([col3_x, 1, 0], aligned_edge=LEFT)
        ans_panel = VGroup(*ans_lines).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        ans_panel.move_to(np.array([3.6, -0.5, 0]))
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "option_analysis_table_spacing" in report.patch_names
    assert "col2_x = -3.25" in patched
    assert "col3_x = 0.65" in patched
    assert ".scale(0.58).move_to([col2_x" in patched
    assert ".scale(0.68).move_to([col3_x" in patched
    assert "ans_panel.scale_to_fit_width(5.7)" in patched
    compile(patched, "candidate.py", "exec")


def test_formula_stack_pressure_patches_local_formula_stack_spacing(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.91,
                        "evidence": [
                            {
                                "category": "text_formula_overlap",
                                "objects": [
                                    {"class": "Text", "text": "第二步：求 y"},
                                    {"class": "MathTex", "text": "3+y=15-3y"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        formula_stack = VGroup()
        def add_formula(tex_str, tracker):
            nonlocal formula_stack
            new_line = MathTex(tex_str, color=FOCUS_COLOR, font_size=36)
            if len(formula_stack) == 0:
                new_line.move_to(left_center + UP * 1.5)
            else:
                new_line.next_to(formula_stack[-1], DOWN, buff=0.4, aligned_edge=LEFT)
            anims = [Write(new_line)]
            if highlight_prev_gray and len(formula_stack) > 0:
                anims.append(formula_stack[-1].animate.set_color(TEXT_COLOR))
            if len(formula_stack) >= 5:
                formula_stack[i].animate.shift(UP * 0.8)
        formula_stack[-1].animate.move_to(left_center + UP * 2.2).set_color(KNOWN_COLOR).set_font_size(28)
        formula_stack = VGroup(formula_stack[-1])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "local_formula_stack_spacing" in report.patch_names
    assert "new_line.move_to(left_center + UP * 0.7)" in patched
    assert "font_size=32" in patched
    assert "new_line.next_to(formula_stack[-1], DOWN" not in patched
    assert "self.play_steps_evenly([FadeOut(formula_stack[-1])], tracker)" in patched
    assert "anims.append(formula_stack[-1].animate.set_color(TEXT_COLOR))" not in patched
    assert "if len(formula_stack) >= 999:" in patched
    assert "formula_stack[i].animate.shift(UP * 1.15)" in patched
    assert "FadeOut(formula_stack[-1])" in patched
    assert "formula_stack = VGroup()" in patched


def test_generic_overlap_patches_right_rule_condition_spacing(tmp_path: Path) -> None:
    _write_brief(tmp_path, "generic_layout_overlap", confidence=0.91)
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        rule_steps = VGroup(rule_step_title, rule_step1, rule_step2, rule_step3).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        rule_steps.next_to(rule_area, DOWN, buff=0.4, aligned_edge=LEFT)
        cond_group1 = VGroup(cond_title, cond_a, cond_1).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        cond_group1.move_to(RIGHT * 3.5 + DOWN * 1.2)
        cond_group2 = VGroup(cond_title2, cond_a2, cond_2).arrange(DOWN, aligned_edge=LEFT, buff=0.15)
        cond_group2.move_to(RIGHT * 3.5 + DOWN * 1.2)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "right_rule_condition_spacing" in report.patch_names
    assert "rule_steps = VGroup(rule_step_title, rule_step1, rule_step2, rule_step3).arrange(DOWN, aligned_edge=LEFT, buff=0.08)" in patched
    assert "rule_steps.next_to(rule_area, DOWN, buff=0.2, aligned_edge=LEFT)" in patched
    assert "cond_group1 = VGroup(cond_title, cond_a, cond_1).arrange(DOWN, aligned_edge=LEFT, buff=0.10)" in patched
    assert "cond_group1.move_to(RIGHT * 3.5 + DOWN * 1.6)" in patched
    assert "cond_group2 = VGroup(cond_title2, cond_a2, cond_2).arrange(DOWN, aligned_edge=LEFT, buff=0.10)" in patched
    assert "cond_group2.move_to(RIGHT * 3.5 + DOWN * 1.6)" in patched


def test_summary_panel_fades_step_formulas(tmp_path: Path) -> None:
    _write_brief(tmp_path, "generic_layout_overlap", confidence=0.91)
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        s1 = MathTex("old1")
        s2 = MathTex("old2")
        s3 = MathTex("old3")
        step1 = MathTex("a")
        step2 = MathTex("b")
        step3 = MathTex("c")
        sol_text = self.make_text("解：")
        tip_panel = self.make_step_panel([
            "方法总结：",
            "先化简"
        ])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "summary_panel_fades_step_formulas" in report.patch_names
    assert "self.play(*[FadeOut(mob) for group in (s1, s2, s3, step1, step2, step3) for mob in group], FadeOut(sol_text))" in patched
    assert patched.index("for group in (s1, s2, s3") < patched.index("tip_panel = self.make_step_panel")


def test_frame_bounds_text_label_adds_safe_box_clamp(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.58,
                        "evidence": [
                            {
                                "category": "frame_bounds_overflow",
                                "objects": [
                                    {
                                        "class": "Text",
                                        "kind": "text",
                                        "text": "y=-0.5x-0.5",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def make_label_text(self, text, anchor=None, direction=UR, font_size=None, color=None, weight=BOLD, buff=0.12, **kwargs):
        mob = self.make_text(str(text))
        if anchor is not None:
            anchor_mob = anchor if isinstance(anchor, Mobject) else Dot(anchor, radius=0.001, fill_opacity=0, stroke_opacity=0)
            mob.next_to(anchor_mob, direction, buff=buff)
        return mob
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "make_label_text_safe_box_clamp" in report.patch_names
    assert "safe_left, safe_right = -6.35, 6.35" in patched
    assert "mob.shift(RIGHT * (safe_left - mob.get_left()[0]))" in patched
    assert "mob.shift(LEFT * (mob.get_right()[0] - safe_right))" in patched


def test_same_origin_text_stack_arranges_multiple_choice_option_row(tmp_path: Path) -> None:
    _write_brief(tmp_path, "same_origin_text_stack", confidence=0.92)
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        problem_panel = self.make_problem_panel([
            self.make_formula_row("已知 ", "x=0"),
            self.make_formula_row("A. 5", "    ", "B. 2", "    ", "C. \\\\sqrt{3}", "    ", "D. \\\\sqrt{6}")
        ])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "multiple_choice_option_row_arrange" in report.patch_names
    assert "VGroup(" in patched
    assert 'self.make_formula_row("A. 5")' in patched
    assert 'self.make_formula_row("D. \\\\sqrt{6}")' in patched
    assert ").arrange(RIGHT, buff=0.62)" in patched


def test_text_container_overflow_fits_left_knowledge_card(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.78,
                        "evidence": [
                            {
                                "category": "text_container_overflow",
                                "objects": [
                                    {"class": "RoundedRectangle", "kind": "container"},
                                    {"class": "MathTex", "kind": "formula", "text": "A \\ge 0, B \\ge 0"},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        left_box = RoundedRectangle(corner_radius=0.2, width=5.2, height=4.6)
        left_title = Text("非负数的性质")
        props = VGroup()
        principle = VGroup()
        left_card = VGroup(left_box, left_title, props, principle)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "left_knowledge_card_fit" in report.patch_names
    assert "card_inner_width = left_box.width - 0.56" in patched
    assert "principle.next_to(props, DOWN, buff=0.25).align_to(left_box, LEFT).shift(RIGHT * 0.28)" in patched


def test_label_obstacle_patch_does_not_leak_geometry_between_methods(tmp_path: Path) -> None:
    _write_brief(tmp_path, "label_shape_overlap")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def make_axes_manual(self):
        square = Square()
        line_axis = Line(LEFT, RIGHT)
        return VGroup(square, line_axis)

    def construct(self):
        axes = self.make_axes_manual()
        dot_a = self.make_point_by_coord(-3, 0)
        label_a = self.make_point_label("A(-3,0)", dot_a, direction=DOWN, obstacles=[axes])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is False
    assert "square" in patched
    assert 'obstacles=[axes, square' not in patched
    assert 'obstacles=[axes, line_axis' not in patched


def test_label_obstacle_patch_does_not_add_multiline_call_keyword_args(tmp_path: Path) -> None:
    _write_brief(tmp_path, "label_shape_overlap")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        axes = self.make_axes_manual()
        arc_A = Arc(
            radius=0.8,
            start_angle=-np.pi/2,
            angle=-np.pi/4,
            arc_center=axes.c2p(0, 0),
            color=BLUE,
        )
        dot_A = Dot()
        lbl_A = self.make_point_label("A", dot_A, direction=DL, obstacles=[axes, arc_A])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert "label_obstacles_from_existing_geometry" not in report.patch_names
    assert "arc_center]" not in patched


def test_label_shape_overlap_moves_adjacent_line_creation_before_label(tmp_path: Path) -> None:
    _write_brief(tmp_path, "label_shape_overlap")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        axes = self.make_axes_manual()
        dot_a = self.make_point_by_coord(-3, 0)
        label_a = self.make_point_label("A(-3,0)", dot_a, direction=DOWN, obstacles=[axes])
        line_ac = self.make_line_by_formula(1, 3)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "label_before_line_creation" in report.patch_names
    assert "line_ac = self.make_line_by_formula(1, 3)\n        label_a = self.make_point_label" in patched
    assert 'obstacles=[axes, line_ac]' in patched


def test_short_point_label_text_overlap_patches_unknown_label_direction(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.82,
                        "evidence": [
                            {
                                "category": "text_formula_overlap",
                                "objects": [
                                    {"class": "Text", "text": "B(3,0)", "center": [-1.78, -0.83]},
                                    {"class": "Text", "text": "G₁", "center": [-1.66, -0.88]},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        lbl_B = self.make_point_label("B(3,0)", dot_B, direction=DR, obstacles=[axes])
        lbl_G1 = self.make_unknown_point_label("G₁", dot_G1, direction=UR, obstacles=[axes, line_BC])
        self.reveal_point_coord(lbl_G1, "G_1", 2, 1, dot_G1, direction=UR, obstacles=[axes, line_BC])
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "short_label_text_overlap_directions" in report.patch_names
    assert "short_label_obstacles_from_existing_labels" in report.patch_names
    assert 'self.make_unknown_point_label("G₁", dot_G1, direction=RIGHT, obstacles=[axes, line_BC, lbl_B])' in patched
    assert 'self.reveal_point_coord(lbl_G1, "G_1", 2, 1, dot_G1, direction=RIGHT, obstacles=[axes, line_BC, lbl_B])' in patched


def test_short_point_label_pair_overlap_patches_direct_text_next_to(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.62,
                        "evidence": [
                            {
                                "category": "text_formula_overlap",
                                "objects": [
                                    {"class": "Text", "text": "Q", "center": [-1.894, -0.866]},
                                    {"class": "Text", "text": "N", "center": [-1.922, -0.795]},
                                ],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        lbl_Q = Text("Q", font_size=16, color=TEXT_COLOR).next_to(Q, DR+LEFT, buff=0.15)
        lbl_N = Text("N", font_size=16, color=TEXT_COLOR).next_to(N, UR, buff=0.15)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "direct_text_label_directions" in report.patch_names
    assert 'lbl_Q = Text("Q", font_size=16, color=TEXT_COLOR).next_to(Q, DOWN, buff=0.55)' in patched
    assert 'lbl_N = Text("N", font_size=16, color=TEXT_COLOR).next_to(N, UR, buff=0.15)' in patched


def test_label_shape_overlap_patches_panel_vertical_spacing(tmp_path: Path) -> None:
    _write_brief(tmp_path, "label_shape_overlap")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        row1 = VGroup(opt_a, opt_b).arrange(RIGHT, buff=1.0)
        row2 = VGroup(opt_c, opt_d).arrange(RIGHT, buff=1.0)
        problem_options = VGroup(row1, row2).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        problem_panel = VGroup(problem_title, problem_options).arrange(DOWN, aligned_edge=LEFT, buff=0.3)
        panel_ab = VGroup(
            calc_a_title, calc_a_eq1, calc_a_eq2, calc_a_res,
            calc_b_title, calc_b_eq1, calc_b_eq2, calc_b_res
        ).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "panel_vertical_spacing" in report.patch_names
    assert "problem_options = VGroup(row1, row2).arrange(DOWN, aligned_edge=LEFT, buff=0.5)" in patched
    assert "problem_panel = VGroup(problem_title, problem_options).arrange(DOWN, aligned_edge=LEFT, buff=0.45)" in patched
    assert ").arrange(DOWN, aligned_edge=LEFT, buff=0.36)" in patched


def test_formula_stack_pressure_compacts_mathtex_assignments(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.82,
                        "evidence": [
                            {
                                "category": "frame_bounds_overflow",
                                "objects": [{"class": "MathTex", "kind": "formula", "text": "=15-2a"}],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        rule_formula2 = MathTex(
            r"|m| = \\begin{cases} m & (m \\ge 0) \\\\ -m & (m < 0) \\end{cases}",
            color=TEXT_COLOR
        ).next_to(rule_title2, DOWN, buff=0.3)
        eq1 = MathTex(r"= |a-4| + |11-a|", color=TEXT_COLOR).move_to([-3.3, 1.5, 0])
        ans1 = MathTex(r"\\text{解：}", color=TEXT_COLOR).next_to(ans_title, DOWN)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert report.patch_names == ["formula_stack_compaction"]
    assert "font_size=30, color=TEXT_COLOR" in patched


def test_formula_stack_pressure_replaces_mathtex_scale_font_size_misuse(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.82,
                        "evidence": [
                            {
                                "category": "frame_bounds_overflow",
                                "objects": [{"class": "MathTex", "kind": "formula", "text": "y=3x-6"}],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        lbl_l1 = MathTex("y=3x-6").scale(FS_LABEL)
        lbl_l2 = MathTex(r"y=\\frac{1}{2}x").scale(GlobalConfig.FS_LABEL)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "mathtex_scale_font_size_misuse" in report.patch_names
    assert 'lbl_l1 = MathTex("y=3x-6", font_size=GlobalConfig.FS_LABEL)' in patched
    assert 'lbl_l2 = MathTex(r"y=\\frac{1}{2}x", font_size=GlobalConfig.FS_LABEL)' in patched


def test_formula_stack_pressure_fades_problem_panel_and_lowers_stack_motion(tmp_path: Path) -> None:
    (tmp_path / "layout_repair_brief.json").write_text(
        json.dumps(
            {
                "clusters": [
                    {
                        "failure_type": "generic_layout_overlap",
                        "confidence": 0.84,
                        "evidence": [
                            {
                                "category": "text_formula_overlap",
                                "objects": [{"class": "MathTex", "text": "a+b"}],
                            },
                            {
                                "category": "frame_bounds_overflow",
                                "objects": [{"class": "SingleStringMathTex", "text": "= 8"}],
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def add_formula_line(self, tex_str):
        if len(self.formula_stack) > 0:
            shift_up = UP * 0.7
        if len(self.formula_stack) == 0:
            new_line.move_to(LEFT * 2 + UP * 0.5)
        else:
            new_line.next_to(self.formula_stack[-1], DOWN, buff=0.3)
            if align_left:
                new_line.align_to(self.formula_stack[-1], LEFT)
            else:
                new_line.shift(RIGHT * 0.5)

    def construct(self):
        problem_panel = VGroup()
        self.formula_stack = VGroup()
        self.max_stack_size = 5
        line1, anims = self.add_formula_line("a+b")
        self.play(a_result.animate.move_to(LEFT * 2 + UP * 1.5))
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "formula_stack_board_lifecycle" in report.patch_names
    assert "formula_stack_board_motion" in report.patch_names
    assert 'self.remove(problem_panel, *getattr(problem_panel, "submobjects", []))\n        line1, anims = self.add_formula_line("a+b")' in patched
    assert "shift_up = UP * 0.65" in patched
    assert "self.max_stack_size = 4" in patched
    assert "new_line.move_to(LEFT * 2 + UP * 0.2)" in patched
    assert "new_line.move_to(LEFT * 2 + DOWN * 1.2)" in patched
    assert "move_to(LEFT * 2 + UP * 0.8)" in patched


def test_step_panel_lifecycle_fades_problem_panel_before_first_step_panel(tmp_path: Path) -> None:
    _write_brief(tmp_path, "step_panel_lifecycle_accumulation")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        problem_panel = self.make_problem_panel([
            "题干第一行",
            "题干第二行",
        ])
        step_panel_1 = self.make_step_panel(["步骤一"])
        step_panel_2 = self.make_step_panel(["步骤二"])
        self.place_panel(step_panel_1)
        self.play(Write(step_panel_1[0]))
        self.play(FadeOut(step_panel_1))
        self.place_panel(step_panel_2)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert report.patch_names == ["problem_panel_fade_before_first_step_panel"]
    assert 'self.remove(problem_panel, *getattr(problem_panel, "submobjects", []))\n        self.place_panel(step_panel_1)' in patched


def test_step_panel_lifecycle_fades_problem_panel_before_generic_panel_name(tmp_path: Path) -> None:
    _write_brief(tmp_path, "step_panel_lifecycle_accumulation")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        problem_panel = self.make_problem_panel(["题干"])
        panel1 = self.make_step_panel(["步骤一"])
        panel2 = self.make_step_panel(["步骤二"])
        self.place_panel(panel1)
        self.play(Write(panel1[0]))
        self.place_panel(panel2)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "problem_panel_fade_before_first_step_panel" in report.patch_names
    assert "step_panel_sequence_fade_previous" in report.patch_names
    assert 'self.remove(problem_panel, *getattr(problem_panel, "submobjects", []))\n        self.place_panel(panel1)' in patched
    assert 'self.remove(panel1, *getattr(panel1, "submobjects", []))\n        self.place_panel(panel2)' in patched


def test_step_panel_lifecycle_fades_previous_step_panel_sequence(tmp_path: Path) -> None:
    _write_brief(tmp_path, "step_panel_lifecycle_accumulation")
    (tmp_path / "candidate.py").write_text(
        """
class Solution:
    def construct(self):
        step_panel_1a = self.make_step_panel(["一"])
        self.place_panel(step_panel_1a)
        self.play(Write(step_panel_1a[0]))
        step_panel_1b = self.make_step_panel(["二"])
        self.place_panel(step_panel_1b)
        self.play(Write(step_panel_1b[0]))
        step_panel_2a = self.make_step_panel(["三"])
        self.place_panel(step_panel_2a)
""".lstrip(),
        encoding="utf-8",
    )

    report = apply_layout_prepatch(tmp_path)

    patched = (tmp_path / "candidate.py").read_text(encoding="utf-8")
    assert report.changed is True
    assert "step_panel_sequence_fade_previous" in report.patch_names
    assert 'self.remove(step_panel_1a, *getattr(step_panel_1a, "submobjects", []))\n        self.place_panel(step_panel_1b)' in patched
    assert 'self.remove(step_panel_1b, *getattr(step_panel_1b, "submobjects", []))\n        self.place_panel(step_panel_2a)' in patched


def test_prepatch_ignores_low_confidence_or_unsupported_brief(tmp_path: Path) -> None:
    _write_brief(tmp_path, "generic_layout_overlap", confidence=0.5)
    original = "class Solution:\n    pass\n"
    (tmp_path / "candidate.py").write_text(original, encoding="utf-8")

    report = apply_layout_prepatch(tmp_path)

    assert report.changed is False
    assert report.patch_names == []
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == original
