import json
from pathlib import Path

from manim_quality.operator.models import CandidateAttempt
from manim_quality.operator.runtime_tools.issues import compact_layout_report
from manim_quality.operator.runtime_tools.workspace import RevisionWorkspace


def _revision(code: str = "class Solution:\n    pass\n") -> CandidateAttempt:
    return CandidateAttempt(
        revision_id="R1",
        parent_revision_id="R0",
        scope=None,
        code=code,
        code_hash="sha256:" + "a" * 64,
        patch_hash=None,
        finding_ids=(),
    )


def test_revision_workspace_materializes_identity_and_code(tmp_path: Path) -> None:
    revision_dir, candidate = RevisionWorkspace(tmp_path).materialize(_revision())

    assert candidate.read_text(encoding="utf-8") == _revision().code
    identity = json.loads(
        (revision_dir / "revision.json").read_text(encoding="utf-8")
    )
    assert identity["revision_id"] == "R1"
    assert identity["code_hash"] == _revision().code_hash


def test_compact_layout_report_returns_only_bounded_issue_facts() -> None:
    issues = [
        {
            "category": "text_formula_overlap",
            "ratio_of_smaller": 0.4,
            "x_overlap": 0.2,
            "y_overlap": 0.3,
            "step": index,
            "a_raw": {
                "path": f"mobjects.{index}",
                "class": "Text",
                "kind": "text",
                "text": "proof",
                "bbox": {"left": 0, "right": 1},
                "points": [[0, 0]] * 100,
            },
            "b_raw": {
                "path": f"mobjects.{index + 1}",
                "class": "MathTex",
                "kind": "formula",
                "text": "x=1",
                "bbox": {"left": 0.8, "right": 2},
            },
        }
        for index in range(25)
    ]

    result = compact_layout_report({"issues": issues}, max_issues=20)

    assert result["blocking_count"] == 25
    assert result["returned_issue_count"] == 20
    assert result["truncated"] is True
    assert "points" not in json.dumps(result)
    assert result["issues"][0]["objects"][0]["path"] == "mobjects.0"
