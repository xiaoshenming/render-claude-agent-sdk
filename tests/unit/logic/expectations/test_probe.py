from evals._expected_relation_probe import evaluate_code, resolve_scene_id
from manim_quality.logic.expectations.schemas import parse_expected_relation_contract


def contract():
    return parse_expected_relation_contract(
        {
            "schema_version": "manim-quality.expected-relations.v1",
            "claims": [
                {
                    "claim_id": "line-ad",
                    "relation": "line_endpoints",
                    "operands": ["AD", "A", "D"],
                    "source_kind": "problem",
                    "evidence": "Connect A to D",
                    "confidence": "explicit",
                }
            ],
        }
    )


def code(endpoint="D"):
    return f"""
import numpy as np
from manim import *
class Solution(Scene):
    def construct(self):
        A = np.array([0, 1, 0])
        D = np.array([0, 0, 0])
        line_AD = Line(A, {endpoint})
"""


def test_probe_binds_contradiction_to_mutated_line() -> None:
    result = evaluate_code(code("LEFT_CENTER"), "Solution", contract(), target_line=8)

    assert result.flagged
    assert result.target_hit
    assert result.counts["contradiction"] == 1


def test_probe_keeps_untouched_control_clean() -> None:
    result = evaluate_code(code(), "Solution", contract())

    assert not result.flagged
    assert result.counts["satisfied"] == 1
    assert result.target_hit is None


def test_probe_resolves_scene_when_legacy_metadata_omits_it() -> None:
    assert resolve_scene_id({}, code()) == "Solution"
    assert resolve_scene_id({"scene_name": "Solution"}, code()) == "Solution"
