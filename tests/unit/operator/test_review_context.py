import json

import pytest

from manim_quality.operator.review_context import load_final_assurance_context


def test_missing_final_assurance_context_is_normal_first_pass(tmp_path):
    assert load_final_assurance_context(tmp_path) == ()


def test_loads_final_assurance_issues(tmp_path):
    payload = {
        "issues": [
            {
                "issue_id": "FA-GEO-1",
                "category": "mathematical_proof",
                "severity": "high",
                "summary": "The visible proof uses the wrong angle pair.",
                "evidence_ids": ["case:risk-frames", "case:final-source"],
            }
        ]
    }
    (tmp_path / "final_assurance_issues.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    assert load_final_assurance_context(tmp_path) == (payload["issues"][0],)


def test_rejects_incomplete_final_assurance_issue(tmp_path):
    (tmp_path / "final_assurance_issues.json").write_text(
        json.dumps({"issues": [{"issue_id": "FA-1"}]}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="missing"):
        load_final_assurance_context(tmp_path)
