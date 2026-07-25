from manim_quality.logic.expectations.comparison import (
    ComparisonStatus,
    compare_expected_relations,
)
from manim_quality.logic.expectations.schemas import parse_expected_relation_contract
from manim_quality.logic.expectations.symbolic_index import build_symbolic_index


def contract(relation, operands):
    return parse_expected_relation_contract(
        {
            "schema_version": "manim-quality.expected-relations.v1",
            "claims": [
                {
                    "claim_id": "claim-1",
                    "relation": relation,
                    "operands": operands,
                    "source_kind": "problem",
                    "evidence": "explicit source statement",
                    "confidence": "explicit",
                }
            ],
        }
    )


def index(line_ad="Line(A, D)"):
    code = f"""
import numpy as np
from manim import *
class Solution(Scene):
    def construct(self):
        A = np.array([0, 2, 0])
        B = np.array([-2, 0, 0])
        C = np.array([2, 0, 0])
        D = np.array([0, 0, 0])
        line_AD = {line_ad}
        line_BC = Line(B, C)
"""
    return build_symbolic_index(code, scene_id="Solution")


def test_detects_symbolic_endpoint_contradiction_without_numeric_endpoint() -> None:
    results = compare_expected_relations(
        contract("line_endpoints", ["AD", "A", "D"]),
        index("Line(A, LEFT_CENTER)"),
    )

    assert results[0].status is ComparisonStatus.CONTRADICTION
    assert results[0].actual == {"start_ref": "A", "end_ref": "LEFT_CENTER"}
    assert results[0].candidate_lines == (10,)


def test_evaluates_virtual_segment_relations_from_points() -> None:
    perpendicular = compare_expected_relations(
        contract("perpendicular", ["AD", "BC"]), index()
    )
    midpoint = compare_expected_relations(
        contract("midpoint", ["D", "B", "C"]), index()
    )

    assert perpendicular[0].status is ComparisonStatus.SATISFIED
    assert midpoint[0].status is ComparisonStatus.SATISFIED


def test_relation_rejects_named_segment_with_wrong_symbolic_endpoints() -> None:
    result = compare_expected_relations(
        contract("perpendicular", ["AD", "BC"]),
        index("Line(A, LEFT_CENTER)"),
    )[0]

    assert result.status is ComparisonStatus.CONTRADICTION
    assert result.actual["semantic_segment"] == "AD"
    assert 10 in result.candidate_lines


def test_numeric_relation_includes_endpoint_definition_lines() -> None:
    result = compare_expected_relations(
        contract("equal_length", ["AB", "AC"]), index()
    )[0]

    assert result.status is ComparisonStatus.SATISFIED
    assert {6, 7, 8}.issubset(result.candidate_lines)


def test_repeated_semantic_segment_flags_any_wrong_representation() -> None:
    geometry = index()
    geometry.lines["line_DA"] = geometry.lines["line_AD"].__class__(
        "line_DA", "D", "B", (0.0, 0.0, 0.0), (-2.0, 0.0, 0.0), 12
    )
    result = compare_expected_relations(
        contract("perpendicular", ["AD", "BC"]), geometry
    )[0]
    assert result.status is ComparisonStatus.CONTRADICTION
    assert 12 in result.candidate_lines


def test_accepts_common_point_variable_aliases_in_named_segments() -> None:
    geometry = index()
    line_type = geometry.lines["line_AD"].__class__
    geometry.lines["line_AD"] = line_type(
        "line_AD", "p_A", "p_D", (0.0, 2.0, 0.0), (0.0, 0.0, 0.0), 10
    )
    result = compare_expected_relations(
        contract("line_endpoints", ["AD", "A", "D"]), geometry
    )[0]

    assert result.status is ComparisonStatus.SATISFIED


def test_rejects_wrong_point_after_normalizing_variable_aliases() -> None:
    geometry = index()
    line_type = geometry.lines["line_AD"].__class__
    geometry.lines["line_AD"] = line_type(
        "line_AD", "p_A", "p_C", (0.0, 2.0, 0.0), (2.0, 0.0, 0.0), 10
    )
    result = compare_expected_relations(
        contract("line_endpoints", ["AD", "A", "D"]), geometry
    )[0]

    assert result.status is ComparisonStatus.CONTRADICTION


def test_fails_closed_when_objects_cannot_be_resolved() -> None:
    result = compare_expected_relations(
        contract("point_on_line", ["F", "BC"]), index()
    )[0]

    assert result.status is ComparisonStatus.UNKNOWN
    assert result.reason_code == "missing_entity"
    assert result.candidate_lines == ()


def test_compares_point_coordinate_and_segment_length() -> None:
    coordinate = compare_expected_relations(
        contract("point_coordinate", ["D", "0", "1", "0"]), index()
    )[0]
    length = compare_expected_relations(
        contract("segment_length", ["BC", "4"]), index()
    )[0]

    assert coordinate.status is ComparisonStatus.CONTRADICTION
    assert coordinate.actual["distance"] == 1.0
    assert length.status is ComparisonStatus.SATISFIED


def test_compares_intersection_membership() -> None:
    satisfied = compare_expected_relations(
        contract("intersection", ["D", "AD", "BC"]), index()
    )[0]
    contradicted = compare_expected_relations(
        contract("intersection", ["A", "AD", "BC"]), index()
    )[0]

    assert satisfied.status is ComparisonStatus.SATISFIED
    assert contradicted.status is ComparisonStatus.CONTRADICTION
    assert contradicted.actual["line_2_normalized_cross"] > 0
