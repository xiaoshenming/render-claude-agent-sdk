from manim import *


class Demo(Scene):
    def construct(self):
        answer = MathTex("18")
        self.play(Write(answer))
