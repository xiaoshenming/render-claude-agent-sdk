from manim import *


class Demo(Scene):
    def construct(self):
        answer = MathTex("24")
        self.play(Write(answer))
