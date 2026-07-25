from manim_quality.layout.policy import layout_invariant_fingerprint


def _fingerprint(source: str) -> str:
    return layout_invariant_fingerprint(source)


def test_unframed_geometry_translation_preserves_layout_semantics() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        A = LEFT * 2 + UP * 1.5
        B = LEFT * 3 + DOWN * 1.5
        C = RIGHT * 2 + DOWN * 1.5
        D = RIGHT * 3 + UP * 1.5
        shape = Polygon(A, B, C, D)
        shape.move_to(LEFT * 3)
"""
    after = """class Lesson(Scene):
    def construct(self):
        A = LEFT * 5.5 + UP * 1.0
        B = LEFT * 6.5 + DOWN * 2.0
        C = LEFT * 1.5 + DOWN * 2.0
        D = LEFT * 0.5 + UP * 1.0
        shape = Polygon(A, B, C, D)
"""

    assert _fingerprint(before) == _fingerprint(after)


def test_point_shape_change_does_not_preserve_layout_semantics() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        A = LEFT * 2 + UP
        B = RIGHT * 2 + UP
        C = DOWN
        shape = Polygon(A, B, C)
"""
    after = before.replace("C = DOWN", "C = DOWN * 2")

    assert _fingerprint(before) != _fingerprint(after)


def test_coordinate_frame_disables_translation_normalization() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        axes = Axes()
        A = LEFT + UP
        B = RIGHT + DOWN
        shape = Line(A, B)
"""
    after = before.replace("A = LEFT + UP", "A = LEFT * 2 + UP").replace(
        "B = RIGHT + DOWN", "B = DOWN"
    )

    assert _fingerprint(before) != _fingerprint(after)


def test_fit_to_canvas_is_a_layout_only_call() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        text = Text('proof')
        self.fit_to_canvas(text, max_width=6)
"""
    after = before.replace("max_width=6", "max_width=5.5")

    assert _fingerprint(before) == _fingerprint(after)


def test_absolute_coordinate_use_disables_translation_normalization() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        A = LEFT + UP
        B = RIGHT + DOWN
        label = DecimalNumber(A[0])
        shape = Line(A, B)
"""
    after = before.replace("A = LEFT + UP", "A = UP").replace(
        "B = RIGHT + DOWN", "B = RIGHT * 2 + DOWN"
    )

    assert _fingerprint(before) != _fingerprint(after)


def test_norm_of_absolute_point_disables_translation_normalization() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        A = LEFT + UP
        B = RIGHT + DOWN
        length = np.linalg.norm(A)
        shape = Line(A, B)
"""
    after = before.replace("A = LEFT + UP", "A = UP").replace(
        "B = RIGHT + DOWN", "B = RIGHT * 2 + DOWN"
    )

    assert _fingerprint(before) != _fingerprint(after)


def test_dimension_guarded_scaling_is_layout_only() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        formula = MathTex('x^2 + y^2 = z^2')
        if formula.width > 5.0:
            formula.scale_to_fit_width(5.0)
        if formula.height > 0.9:
            formula.scale_to_fit_height(0.9)
        group = VGroup(formula).move_to(DOWN)
"""
    after = """class Lesson(Scene):
    def construct(self):
        formula = MathTex('x^2 + y^2 = z^2')
        group = VGroup(formula).scale(0.7).move_to(DOWN)
"""

    assert _fingerprint(before) == _fingerprint(after)


def test_dimension_branch_with_content_change_is_not_layout_only() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        formula = MathTex('x^2 + y^2 = z^2')
        if formula.width > 5.0:
            formula = MathTex('x^2 + y^2 = c^2')
"""
    after = """class Lesson(Scene):
    def construct(self):
        formula = MathTex('x^2 + y^2 = z^2')
"""

    assert _fingerprint(before) != _fingerprint(after)


def test_removing_transform_source_copy_changes_layout_semantics() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        self.play(ReplacementTransform(source.copy(), target))
"""
    after = """class Lesson(Scene):
    def construct(self):
        self.play(ReplacementTransform(source, target))
"""

    assert _fingerprint(before) != _fingerprint(after)


def test_nested_computation_in_layout_call_remains_semantic() -> None:
    before = """class Lesson(Scene):
    def construct(self):
        shape.move_to(compute_anchor())
"""
    after = """class Lesson(Scene):
    def construct(self):
        shape.move_to(compute_answer())
"""

    assert _fingerprint(before) != _fingerprint(after)
