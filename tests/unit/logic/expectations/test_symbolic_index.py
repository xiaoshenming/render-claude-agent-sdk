from manim_quality.logic.expectations.symbolic_index import build_symbolic_index

CODE = """
import numpy as np
from manim import *

class Solution(Scene):
    def construct(self):
        A = np.array([0, 2, 0])
        B = np.array([-2, 0, 0])
        C = np.array([2, 0, 0])
        D = np.array([0, 0, 0])
        line_AD = Line(A, LEFT_CENTER)
        line_BC = Line(B, C)
"""


def test_indexes_points_and_symbolic_line_endpoints() -> None:
    index = build_symbolic_index(CODE, scene_id="Solution")

    assert index.points["A"].position == (0.0, 2.0, 0.0)
    assert index.lines["line_AD"].start_ref == "A"
    assert index.lines["line_AD"].end_ref == "LEFT_CENTER"
    assert index.lines["line_AD"].line_start == 11


def test_resolves_semantic_aliases_and_virtual_segments() -> None:
    index = build_symbolic_index(CODE, scene_id="Solution")

    assert index.resolve_named_line("AD").object_id == "line_AD"
    virtual = index.resolve_segment("AC")
    assert virtual.start == (0.0, 2.0, 0.0)
    assert virtual.end == (2.0, 0.0, 0.0)


def test_resolves_explicit_segment_with_non_letter_point_names() -> None:
    code = CODE.replace("A =", "A_p =").replace("C =", "C_p =")
    index = build_symbolic_index(code, scene_id="Solution")

    virtual = index.resolve_segment("A_p:C_p")

    assert virtual is not None
    assert virtual.start == (0.0, 2.0, 0.0)
    assert virtual.end == (2.0, 0.0, 0.0)


def test_resolves_undirected_segment_alias_in_either_endpoint_order() -> None:
    code = CODE.replace("line_AD", "line_DA")
    index = build_symbolic_index(code, scene_id="Solution")

    assert index.resolve_named_line("AD").object_id == "line_DA"


def test_finds_all_named_lines_for_repeated_semantic_segment() -> None:
    code = CODE.replace(
        "line_BC = Line(B, C)",
        "line_BC = Line(B, C)\n        line_DA = Line(D, A)",
    )
    index = build_symbolic_index(code, scene_id="Solution")

    assert {item.object_id for item in index.find_named_lines("AD")} == {
        "line_AD",
        "line_DA",
    }


def test_returns_none_for_ambiguous_segment_or_dynamic_point() -> None:
    code = CODE.replace(
        "D = np.array([0, 0, 0])",
        "D = np.array([0, 0, 0])\n        D.shift(RIGHT)",
    )
    index = build_symbolic_index(code, scene_id="Solution")

    assert index.resolve_segment("AD") is None
    assert index.resolve_segment("UNKNOWN") is None
