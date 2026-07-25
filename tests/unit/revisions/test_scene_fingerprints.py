from manim_quality.revisions.fingerprint import scene_fingerprints

SOURCE = """
def shared_helper(value):
    return value + 1

class Second(Scene):
    def construct(self):
        self.play(Create(Circle()))

class First(MovingCameraScene):
    def construct(self):
        self.play(Write(Text("first")))
"""


def test_scene_fingerprints_are_sorted_and_stable_across_formatting() -> None:
    reformatted = SOURCE.replace("\nclass Second", "\n\n\nclass Second").replace(
        "Create(Circle())", "Create( Circle() )"
    )

    fingerprints = scene_fingerprints(SOURCE)

    assert list(fingerprints) == ["First", "Second"]
    assert fingerprints == scene_fingerprints(reformatted)


def test_scene_change_only_changes_that_scene_hash() -> None:
    changed = SOURCE.replace('Text("first")', 'Text("changed")')

    before = scene_fingerprints(SOURCE)
    after = scene_fingerprints(changed)

    assert before["First"] != after["First"]
    assert before["Second"] == after["Second"]


def test_shared_helper_change_is_not_guessed_into_scene_hashes() -> None:
    changed = SOURCE.replace("value + 1", "value + 2")

    assert scene_fingerprints(SOURCE) == scene_fingerprints(changed)


def test_local_scene_subclasses_and_construct_classes_are_detected() -> None:
    source = """
class BaseLesson(Scene):
    pass

class DerivedLesson(BaseLesson):
    def construct(self):
        pass

class ConventionBased:
    def construct(self):
        pass
"""

    assert list(scene_fingerprints(source)) == [
        "BaseLesson",
        "ConventionBased",
        "DerivedLesson",
    ]
