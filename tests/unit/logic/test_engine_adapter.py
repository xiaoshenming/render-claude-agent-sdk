import json
from copy import deepcopy
from pathlib import Path

import pytest

from manim_quality.logic.engine_adapter import (
    ENGINE_EXTRACTOR_IDENTITY,
    build_engine_review_evidence,
    validate_engine_review_evidence,
    verify_engine_review_evidence,
)
from manim_quality.revisions.fingerprint import code_hash

VALID_EVIDENCE = {
    "schema_version": "manim-quality.logic-engine-evidence.v1",
    "candidate_code_hash": "sha256:" + "a" * 64,
    "extractor_identity": ENGINE_EXTRACTOR_IDENTITY,
    "current_sample_evidence": {"source": "none"},
    "scene_classes": [],
    "visible_math_claims": [],
    "deterministic_logic_facts": {},
    "focused_code_excerpts": [],
    "helper_method_excerpts": [],
    "input_policy": {
        "historical_reports_included": False,
        "external_diagnosis_included": False,
        "repair_hints_included": False,
        "purpose": "current_sample_logic_review_only",
    },
}


def test_engine_adapter_reuses_frozen_current_sample_facts(tmp_path: Path) -> None:
    code = """from manim import *

class Demo(Scene):
    def make_label(self):
        return MathTex(r"AB = 2")

    def construct(self):
        point_A = make_point_by_coord(0, 0)
        point_B = make_point_by_coord(2, 2)
        line_AB = make_line_by_formula(0, 0, x_range=[0, 2])
        self.add(self.make_label())
"""
    (tmp_path / "candidate.py").write_text(code, encoding="utf-8")
    (tmp_path / "problem_text.txt").write_text(
        "Draw line AB through A(0, 0) and B(2, 2).",
        encoding="utf-8",
    )
    (tmp_path / "case_manifest.json").write_text(
        json.dumps(
            {
                "scene_name": "Demo",
                "visible_error_description": "Line AB misses point B.",
                "server_refs": ["must-not-leak"],
            }
        ),
        encoding="utf-8",
    )

    evidence = build_engine_review_evidence(tmp_path)

    assert set(evidence) == {
        "schema_version",
        "candidate_code_hash",
        "extractor_identity",
        "current_sample_evidence",
        "scene_classes",
        "visible_math_claims",
        "deterministic_logic_facts",
        "focused_code_excerpts",
        "helper_method_excerpts",
        "input_policy",
    }
    assert "sample_id" not in evidence
    assert "code_excerpt" not in evidence
    encoded = json.dumps(evidence)
    assert "server_refs" not in encoded
    assert "Line AB misses point B" not in encoded
    assert "exact_code_after" not in encoded
    assert "line_replacements" not in encoded
    assert evidence["deterministic_logic_facts"]["line_endpoint_mismatch_count"] == 1
    assert evidence["current_sample_evidence"] == {
        "source": "bounded_scene_identity",
        "scene_name": "Demo",
    }
    assert evidence["candidate_code_hash"] == code_hash(code)
    assert evidence["extractor_identity"] == ENGINE_EXTRACTOR_IDENTITY
    assert evidence["input_policy"]["historical_reports_included"] is False


@pytest.mark.parametrize(
    "case",
    ["missing_field", "wrong_version", "unsafe_policy", "repair_hint"],
)
def test_engine_adapter_rejects_invalid_or_polluted_contract(case: str) -> None:
    evidence = deepcopy(VALID_EVIDENCE)
    if case == "missing_field":
        evidence.pop("scene_classes")
    elif case == "wrong_version":
        evidence["schema_version"] = "unsupported"
    elif case == "unsafe_policy":
        evidence["input_policy"]["external_diagnosis_included"] = True
    else:
        evidence["focused_code_excerpts"] = [{"exact_code_after": "bad"}]

    with pytest.raises(ValueError):
        validate_engine_review_evidence(evidence)


def test_engine_adapter_rejects_extra_current_sample_fields() -> None:
    evidence = deepcopy(VALID_EVIDENCE)
    evidence["current_sample_evidence"] = {
        "source": "bounded_scene_identity",
        "scene_name": "Demo",
        "ground_truth": "must-not-enter-prompt",
    }

    with pytest.raises(ValueError, match="current_sample_evidence"):
        validate_engine_review_evidence(evidence)


def test_engine_adapter_requires_candidate_and_ignores_malformed_manifest(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="candidate.py"):
        build_engine_review_evidence(tmp_path)

    (tmp_path / "candidate.py").write_text(
        "from manim import *\n"
        "class Demo(Scene):\n"
        "    def construct(self):\n"
        "        pass\n",
        encoding="utf-8",
    )
    (tmp_path / "case_manifest.json").write_bytes(b"\xff\xfe")

    evidence = build_engine_review_evidence(tmp_path)

    assert evidence["current_sample_evidence"] == {"source": "none"}


def test_engine_adapter_rejects_fabricated_code_derived_excerpts(
    tmp_path: Path,
) -> None:
    code = (
        "from manim import *\n"
        "class Demo(Scene):\n"
        "    def construct(self):\n"
        "        self.add(MathTex('x=10'))\n"
    )
    (tmp_path / "candidate.py").write_text(code, encoding="utf-8")
    evidence = build_engine_review_evidence(tmp_path)
    evidence["visible_math_claims"] = [
        {
            "line": 4,
            "value": "x=999",
            "score": 10,
            "source": "scene_string_literal",
        }
    ]

    with pytest.raises(ValueError, match="code-derived evidence"):
        verify_engine_review_evidence(code, evidence)
