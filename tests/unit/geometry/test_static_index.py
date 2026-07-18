import pytest

from manim_quality.geometry.static_index import build_static_geometry_snapshot
from manim_quality.revisions.fingerprint import code_hash

CODE = """from manim import *
import numpy as np

class Solution(Scene):
    def construct(self):
        A = np.array([-2.0, 0.0, 0.0])
        B = np.array([2.0, 0.0, 0.0])
        C = np.array([0.0, 1.0, 0.0])
        line_ab = Line(A, B)
        dot_c = Dot(C)
        circle = Circle(radius=1.0)
        triangle = Polygon(A, B, C)
"""


def test_static_index_extracts_source_bound_supported_objects() -> None:
    snapshot = build_static_geometry_snapshot(CODE, scene_id="Solution")

    assert snapshot.code_hash == code_hash(CODE)
    assert snapshot.provenance == "static_initial_state"
    assert snapshot.object("A").state["position"] == (-2.0, 0.0, 0.0)
    assert snapshot.object("line_ab").state["start_ref"] == "A"
    assert snapshot.object("line_ab").state["end"] == (2.0, 0.0, 0.0)
    assert snapshot.object("dot_c").state["position"] == (0.0, 1.0, 0.0)
    assert snapshot.object("circle").state["radius"] == 1.0
    assert len(snapshot.object("triangle").state["vertices"]) == 3
    assert snapshot.object("line_ab").source.scene_id == "Solution"
    assert "Line(A, B)" in snapshot.object("line_ab").source.excerpt


@pytest.mark.parametrize(
    "statement",
    [
        "line_ab.shift(UP)",
        "line_ab.rotate(0.5)",
        "line_ab.add_updater(lambda m: m.shift(RIGHT))",
    ],
)
def test_post_construction_geometry_changes_become_unknown(statement: str) -> None:
    code = CODE + f"        {statement}\n"

    snapshot = build_static_geometry_snapshot(code, scene_id="Solution")

    changed = snapshot.object("line_ab")
    assert changed.status.value == "unknown"
    assert changed.reason_code == "dynamic_value"
    assert changed.state == {}


def test_unknown_helper_and_nonliteral_values_are_never_executed_or_guessed() -> None:
    code = """from manim import *
import numpy as np

class Solution(Scene):
    def construct(self):
        A = np.array([dynamic_x(), 0, 0])
        B = np.array([1, 0, 0])
        line_ab = Line(A, B)
"""

    snapshot = build_static_geometry_snapshot(code, scene_id="Solution")

    assert snapshot.object("A").status.value == "unknown"
    assert snapshot.object("line_ab").status.value == "unknown"


def test_reassignment_is_ambiguous_instead_of_silently_selecting_one_value() -> None:
    code = """from manim import *
import numpy as np

class Solution(Scene):
    def construct(self):
        A = np.array([0, 0, 0])
        A = np.array([1, 0, 0])
"""

    snapshot = build_static_geometry_snapshot(code, scene_id="Solution")

    assert snapshot.object("A").status.value == "unknown"
    assert snapshot.object("A").reason_code == "unresolved_reference"


def test_missing_scene_is_rejected() -> None:
    with pytest.raises(ValueError, match="Scene"):
        build_static_geometry_snapshot(CODE, scene_id="Missing")


def test_scene_lines_can_resolve_literal_module_geometry_constants() -> None:
    code = """from manim import *
import numpy as np

LEFT_CENTER = [-3.0, 0.0, 0.0]

class Solution(Scene):
    def construct(self):
        B = np.array([0.0, 0.0, 0.0])
        line = Line(B, LEFT_CENTER)
"""

    snapshot = build_static_geometry_snapshot(code, scene_id="Solution")

    assert snapshot.object("LEFT_CENTER").state["position"] == (-3.0, 0.0, 0.0)
    assert snapshot.object("line").status.value == "known"
    assert snapshot.object("line").state["end_ref"] == "LEFT_CENTER"


def test_unexecuted_branch_assignment_is_not_indexed_as_known() -> None:
    code = """from manim import *
import numpy as np

class Solution(Scene):
    def construct(self):
        if False:
            ghost = np.array([1, 2, 0])
"""

    snapshot = build_static_geometry_snapshot(code, scene_id="Solution")

    with pytest.raises(KeyError):
        snapshot.object("ghost")


@pytest.mark.parametrize(
    "mutation",
    [
        "A[0] = 5",
        "dot.animate.shift(RIGHT)",
        "line.put_start_and_end_on(B, A)",
    ],
)
def test_unmodeled_geometry_mutations_invalidate_static_facts(mutation: str) -> None:
    code = f"""from manim import *
import numpy as np

class Solution(Scene):
    def construct(self):
        A = np.array([0, 0, 0])
        B = np.array([1, 0, 0])
        dot = Dot(A)
        line = Line(A, B)
        {mutation}
"""

    snapshot = build_static_geometry_snapshot(code, scene_id="Solution")

    changed_name = "A" if mutation.startswith("A[") else mutation.split(".")[0]
    assert snapshot.object(changed_name).status.value == "unknown"
    assert snapshot.object(changed_name).reason_code == "dynamic_value"
