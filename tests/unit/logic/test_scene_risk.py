from manim_quality.logic.diff_guard import DiffGuardResult
from manim_quality.logic.validators.scene_risk import new_scene_risks
from manim_quality.revisions.fingerprint import sha256_text


def diff() -> DiffGuardResult:
    return DiffGuardResult(True, ("Demo",), (), sha256_text("patch"))


def test_scene_risk_detects_subprocess_call() -> None:
    before = """import subprocess

class Demo(Scene):
    def construct(self):
        self.add(Text("safe"))
"""
    after = before.replace(
        'self.add(Text("safe"))',
        'subprocess.call(["tool"])\n        self.add(Text("safe"))',
    )

    assert "process" in new_scene_risks(before, after, diff())


def test_scene_risk_detects_changed_existing_file_operation() -> None:
    before = """class Demo(Scene):
    def construct(self):
        open("first.txt")
"""
    after = before.replace("first.txt", "second.txt")

    assert "file_io" in new_scene_risks(before, after, diff())


def test_scene_risk_detects_dangerous_capability_aliased_inside_scene() -> None:
    before = """import subprocess

class Demo(Scene):
    def construct(self):
        self.add(Text("safe"))
"""
    after = before.replace(
        'self.add(Text("safe"))',
        'runner = subprocess.call\n        runner(["tool"])',
    )

    assert "process" in new_scene_risks(before, after, diff())


def test_scene_risk_detects_activation_of_existing_dangerous_alias() -> None:
    before = """import subprocess

class Demo(Scene):
    def construct(self):
        runner = subprocess.call
        self.add(Text("safe"))
"""
    after = before.replace(
        'self.add(Text("safe"))',
        'runner(["tool"])\n        self.add(Text("safe"))',
    )

    assert "process" in new_scene_risks(before, after, diff())
