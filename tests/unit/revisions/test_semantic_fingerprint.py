import pytest

from manim_quality.revisions.fingerprint import (
    PythonSyntaxError,
    semantic_fingerprint,
)

BASE = """
class Lesson(Scene):
    def construct(self):
        value = 2
        formula = MathTex("x^2")
        point = Dot((1, 2, 0))
        if value > 1:
            self.play(Write(formula))
"""


def changed(old: str, new: str) -> None:
    assert semantic_fingerprint(old) != semantic_fingerprint(new)


def test_whitespace_comments_and_line_numbers_do_not_change_fingerprint() -> None:
    reformatted = """
# leading comment

class Lesson(Scene):

    def construct(self):
        value=2
        formula = MathTex( "x^2" )
        point = Dot((1,2,0))
        if value > 1:  # inline comment
            self.play(Write(formula))
"""

    assert semantic_fingerprint(BASE) == semantic_fingerprint(reformatted)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("value = 2", "value = 3"),
        ('MathTex("x^2")', 'MathTex("x^3")'),
        ("Dot((1, 2, 0))", "Dot((2, 2, 0))"),
        ("if value > 1:", "if value >= 1:"),
        ("Write(formula)", "FadeIn(formula)"),
    ],
)
def test_semantic_changes_change_fingerprint(old: str, new: str) -> None:
    changed(BASE, BASE.replace(old, new))


def test_syntax_errors_have_clear_location() -> None:
    with pytest.raises(PythonSyntaxError, match=r"line 2.*invalid syntax"):
        semantic_fingerprint("\nclass Lesson(:\n    pass\n")
