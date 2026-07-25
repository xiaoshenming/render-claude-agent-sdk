from __future__ import annotations

import json

from _reviewer_support import setup_evidence

from manim_quality.logic.review_digest import (
    REVIEW_DIGEST_SCHEMA_VERSION,
    build_review_digest,
)

GEOMETRY_CODE = """from manim import *
import numpy as np

class ProofScene(Scene):
    def construct(self):
        A = np.array([-2.5, 2.0, 0])
        B = np.array([-5.0, -0.3, 0])
        line_ab = Line(A, B)
        angle_c = self.make_angle_with_label(Line(B, A), Line(B, B), label="α")
        title = Tex(r"两条割线")
        self.add(line_ab, angle_c, title)
"""


def test_digest_contains_bounded_math_facts_without_source_duplication(
    tmp_path,
) -> None:
    _, _, evidence = setup_evidence(tmp_path, code=GEOMETRY_CODE)

    digest = build_review_digest(evidence, GEOMETRY_CODE).to_prompt_dict()
    encoded = json.dumps(digest, ensure_ascii=False, separators=(",", ":"))

    assert digest["schema_version"] == REVIEW_DIGEST_SCHEMA_VERSION
    assert {item["name"] for item in digest["numeric_vectors"]} == {"A", "B"}
    assert {item["constructor"] for item in digest["constructions"]} >= {
        "Line",
        "make_angle_with_label",
        "Tex",
    }
    assert all("line" in item for item in digest["constructions"])
    assert "focused_code_excerpts" not in encoded
    assert "helper_method_excerpts" not in encoded
    assert "exact_code_after" not in encoded
    assert GEOMETRY_CODE not in encoded


def test_digest_is_deterministic_and_facts_not_fixes(tmp_path) -> None:
    _, _, evidence = setup_evidence(tmp_path, code=GEOMETRY_CODE)

    first = build_review_digest(evidence, GEOMETRY_CODE).to_prompt_dict()
    second = build_review_digest(evidence, GEOMETRY_CODE).to_prompt_dict()

    assert first == second
    assert first["input_policy"] == {
        "external_diagnosis_included": False,
        "repair_hints_included": False,
        "full_source_embedded": False,
        "candidate_readable_on_demand": True,
    }


def test_digest_is_smaller_than_current_prompt_evidence(tmp_path) -> None:
    _, _, evidence = setup_evidence(tmp_path, code=GEOMETRY_CODE)
    current = json.dumps(
        evidence.to_prompt_dict(), ensure_ascii=False, separators=(",", ":")
    )
    digest = json.dumps(
        build_review_digest(evidence, GEOMETRY_CODE).to_prompt_dict(),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    assert len(digest) < len(current)
