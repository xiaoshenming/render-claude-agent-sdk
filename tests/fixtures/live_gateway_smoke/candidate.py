from manim import MathTex, Scene, Write

AUTHORITATIVE_PROBLEM_TEXT = "解方程 x+1=2。"
EXPECTED_SOLUTION = "移项可得 x=1。"


class BaseConfigScene(Scene):
    pass


class Solution(BaseConfigScene):
    def construct(self):
        answer = MathTex("x=3")
        self.play(Write(answer))
