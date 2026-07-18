from manim import *
import numpy as np

class GlobalConfig:
    BG_COLOR = "#F7F1E8"
    BASE_COLOR = "#1F2933"
    DRAW_COLOR = "#2F6F9F"
    KNOWN_COLOR = "#2E8B57"
    FOCUS_COLOR = "#D98A1F"
    RESULT_COLOR = "#C94C4C"
    TEXT_COLOR = "#263238"
    AUX_COLOR = "#E7EEF2"
    FONT = "Microsoft YaHei"
    RANDOM_SEED = 42

class BaseConfigScene(Scene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Tex.set_default(tex_template=TexTemplateLibrary.ctex)
        self.camera.background_color = GlobalConfig.BG_COLOR
        np.random.seed(GlobalConfig.RANDOM_SEED)
        self._elapsed_estimate = 0.0

    def make_text(self, text, font_size=28, color=None, t2c=None):
        return Text(
            str(text),
            font=GlobalConfig.FONT,
            font_size=font_size,
            color=color or GlobalConfig.TEXT_COLOR,
            t2c=t2c or {},
            disable_ligatures=True,
        )

    def make_wrapped_text(self, text, font_size=24, max_chars=18, color=None):
        text = str(text)
        lines, current = [], ""
        for ch in text:
            current += ch
            if len(current) >= max_chars:
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
        group = VGroup(*[self.make_text(line, font_size=font_size, color=color) for line in lines])
        group.arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        return group

    def show(self, mob, run_time=0.8, hold=0.8):
        self.play(FadeIn(mob, shift=UP * 0.06), run_time=run_time)
        self._elapsed_estimate += run_time
        self.pause(hold)

    def tracked_play(self, *animations, run_time=0.8, **kwargs):
        self.play(*animations, run_time=run_time, **kwargs)
        self._elapsed_estimate += run_time

    def pause(self, seconds=0.8):
        seconds = max(0.2, min(1.5, seconds))
        self.wait(seconds)
        self._elapsed_estimate += seconds

    def ensure_min_duration(self, min_seconds=45):
        remaining = min_seconds - self._elapsed_estimate
        if remaining > 0:
            self.wait(remaining)

    def safe_layout(self, obj):
        if obj.width > 12:
            obj.scale_to_fit_width(12)
        if obj.height > 6.5:
            obj.scale_to_fit_height(6.5)
        return obj

    def persistent_clone(self, mob, color=None, stroke_width=5, opacity=1.0):
        clone = mob.copy()
        try:
            clone.set_color(color or GlobalConfig.KNOWN_COLOR)
        except Exception:
            pass
        try:
            clone.set_stroke(color=color or GlobalConfig.KNOWN_COLOR, width=stroke_width, opacity=opacity)
        except Exception:
            pass
        return clone

    def sweep_mobject(self, mob, color=None, stroke_width=8, run_time=0.7):
        highlight = mob.copy()
        try:
            highlight.set_color(color or GlobalConfig.FOCUS_COLOR)
            highlight.set_stroke(color=color or GlobalConfig.FOCUS_COLOR, width=stroke_width, opacity=0.9)
        except Exception:
            pass
        self.play(ShowPassingFlash(highlight, time_width=0.7), run_time=run_time)
        self._elapsed_estimate += run_time

    def pulse_mobject(self, mob, color=None, scale_factor=1.08, run_time=0.6):
        self.play(Indicate(mob, color=color or GlobalConfig.FOCUS_COLOR, scale_factor=scale_factor), run_time=run_time)
        self._elapsed_estimate += run_time

    def flash_point(self, point_mob, color=None, run_time=0.6):
        self.play(Flash(point_mob, color=color or GlobalConfig.FOCUS_COLOR, flash_radius=0.35), run_time=run_time)
        self._elapsed_estimate += run_time

    def make_angle_mark(self, line1, line2, radius=0.28, color=None):
        return Angle(line1, line2, radius=radius, color=color or GlobalConfig.KNOWN_COLOR, stroke_width=4)

    def make_tick_mark(self, line, alpha=0.5, size=0.12, color=None):
        start, end = line.get_start(), line.get_end()
        pos = start + (end - start) * alpha
        direction = end - start
        norm = np.linalg.norm(direction)
        if norm < 1e-6:
            direction = RIGHT
        else:
            direction = direction / norm
        normal = np.array([-direction[1], direction[0], 0])
        return Line(
            start=pos - normal * size,
            end=pos + normal * size,
            color=color or GlobalConfig.KNOWN_COLOR,
            stroke_width=4,
        )

    def safe_add_watermark(self):
        if "_add_hammerath_watermarks" in globals():
            _add_hammerath_watermarks(self, "HAMMERATH", "user_14660640")

class Solution(BaseConfigScene):
    def construct(self):
        # 1. Title & Problem Statement
        prob_text = self.make_text("已知: AB = DC, ∠ABC = ∠DCB. 求证: △ABC ≅ △DCB, AC = DB.", font_size=22)
        prob_text.to_edge(UP, buff=0.3)
        sep_line = Line(start=[-6.5, 2.4, 0], end=[6.5, 2.4, 0], stroke_width=1, color=GlobalConfig.AUX_COLOR)
        
        self.show(prob_text)
        self.play(Create(sep_line))
        
        # 2. Geometry setup
        p_A = np.array([-3.0, 1.2, 0])
        p_B = np.array([-3.5, -1.8, 0])
        p_C = np.array([-0.5, -1.8, 0])
        p_D = np.array([-1.0, 1.2, 0])
        
        dot_A = Dot(p_A, color=GlobalConfig.BASE_COLOR)
        dot_B = Dot(p_B, color=GlobalConfig.BASE_COLOR)
        dot_C = Dot(p_C, color=GlobalConfig.BASE_COLOR)
        dot_D = Dot(p_D, color=GlobalConfig.BASE_COLOR)
        
        label_A = self.make_text("A", font_size=20).next_to(p_A, UP+LEFT, buff=0.15)
        label_B = self.make_text("B", font_size=20).next_to(p_B, DOWN+LEFT, buff=0.15)
        label_C = self.make_text("C", font_size=20).next_to(p_C, DOWN+RIGHT, buff=0.15)
        label_D = self.make_text("D", font_size=20).next_to(p_D, UP+RIGHT, buff=0.15)
        
        line_AB = Line(p_A, p_B, color=GlobalConfig.BASE_COLOR)
        line_BC = Line(p_B, p_C, color=GlobalConfig.BASE_COLOR)
        line_CA = Line(p_C, p_A, color=GlobalConfig.BASE_COLOR)
        line_DC = Line(p_D, p_C, color=GlobalConfig.BASE_COLOR)
        line_DB = Line(p_D, p_C, color=GlobalConfig.BASE_COLOR)
        
        self.play(
            Create(VGroup(line_AB, line_BC, line_CA, line_DC, line_DB)),
            FadeIn(VGroup(dot_A, dot_B, dot_C, dot_D, label_A, label_B, label_C, label_D))
        )
        self.pause(0.8)
        
        # 3. Highlight knowns
        # AB = DC
        self.sweep_mobject(line_AB)
        self.sweep_mobject(line_DC)
        tick_AB = self.make_tick_mark(line_AB, color=GlobalConfig.KNOWN_COLOR)
        tick_DC = self.make_tick_mark(line_DC, color=GlobalConfig.KNOWN_COLOR)
        self.play(Create(tick_AB), Create(tick_DC))
        
        # ∠ABC = ∠DCB
        self.flash_point(dot_B)
        self.flash_point(dot_C)
        line_B_C = Line(p_B, p_C)
        line_B_A = Line(p_B, p_A)
        angle_ABC = Angle(line_B_C, line_B_A, radius=0.4, color=GlobalConfig.KNOWN_COLOR)
        line_C_D = Line(p_C, p_D)
        line_C_B = Line(p_C, p_B)
        angle_DCB = Angle(line_C_D, line_C_B, radius=0.4, color=GlobalConfig.KNOWN_COLOR)
        self.play(Create(angle_ABC), Create(angle_DCB))
        self.pause(0.8)
        
        # 4. Proof steps on the right
        step1 = self.make_text("在 △ABC 和 △DCB 中：", font_size=20)
        step2 = self.make_text("①  AB = DC  (已知)", font_size=18, t2c={"AB = DC": GlobalConfig.KNOWN_COLOR})
        step3 = self.make_text("②  ∠ABC = ∠DCB  (已知)", font_size=18, t2c={"∠ABC = ∠DCB": GlobalConfig.KNOWN_COLOR})
        step4 = self.make_text("③  BC = CB  (公共边)", font_size=18, t2c={"BC = CB": GlobalConfig.KNOWN_COLOR})
        step5 = self.make_text("∴ △ABC ≅ △DCB  (SAS)", font_size=20, color=GlobalConfig.RESULT_COLOR)
        step6 = self.make_text("∴ AC = DB  (对应边相等)", font_size=20, color=GlobalConfig.RESULT_COLOR)
        
        proof_group = VGroup(step1, step2, step3, step4, step5, step6).arrange(DOWN, aligned_edge=LEFT, buff=0.25)
        proof_group.move_to(np.array([3.2, -0.2, 0]))
        
        self.play(Write(step1))
        self.pause(0.6)
        
        self.play(Write(step2))
        self.sweep_mobject(line_AB)
        self.sweep_mobject(line_DC)
        self.pause(0.6)
        
        self.play(Write(step3))
        self.pulse_mobject(angle_ABC)
        self.pulse_mobject(angle_DCB)
        self.pause(0.6)
        
        self.play(Write(step4))
        self.sweep_mobject(line_BC)
        line_BC_green = Line(p_B, p_C, color=GlobalConfig.KNOWN_COLOR, stroke_width=4)
        self.play(Create(line_BC_green))
        self.pause(0.8)
        
        self.play(Write(step5))
        poly_ABC = Polygon(p_A, p_B, p_C, fill_color=GlobalConfig.RESULT_COLOR, fill_opacity=0.12, stroke_width=0)
        poly_DCB = Polygon(p_D, p_C, p_B, fill_color=GlobalConfig.RESULT_COLOR, fill_opacity=0.12, stroke_width=0)
        border_ABC = Polygon(p_A, p_B, p_C, color=GlobalConfig.RESULT_COLOR, stroke_width=2.5)
        border_DCB = Polygon(p_D, p_C, p_B, color=GlobalConfig.RESULT_COLOR, stroke_width=2.5)
        self.play(FadeIn(poly_ABC), FadeIn(poly_DCB), Create(border_ABC), Create(border_DCB))
        self.pause(1.0)
        
        self.play(Write(step6))
        self.sweep_mobject(line_CA, color=GlobalConfig.RESULT_COLOR)
        self.sweep_mobject(line_DB, color=GlobalConfig.RESULT_COLOR)
        tick_AC = VGroup(
            self.make_tick_mark(line_CA, alpha=0.4, size=0.1, color=GlobalConfig.RESULT_COLOR),
            self.make_tick_mark(line_CA, alpha=0.46, size=0.1, color=GlobalConfig.RESULT_COLOR)
        )
        tick_DB = VGroup(
            self.make_tick_mark(line_DB, alpha=0.4, size=0.1, color=GlobalConfig.RESULT_COLOR),
            self.make_tick_mark(line_DB, alpha=0.46, size=0.1, color=GlobalConfig.RESULT_COLOR)
        )
        self.play(Create(tick_AC), Create(tick_DB))
        self.pause(2.0)
        
        self.safe_add_watermark()
        self.ensure_min_duration(45)

# === END ===
