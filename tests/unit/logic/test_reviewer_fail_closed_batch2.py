from dataclasses import replace
from pathlib import Path

import pytest
from _reviewer_support import (
    CODE,
    MemorySink,
    PayloadBackend,
    add_citation,
    candidate_citation,
    issue_entry,
    issue_payload,
    limits,
    reviewer,
    service,
    setup_evidence,
)

from manim_quality.agents.profile import coder_profile, reviewer_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.logic._errors import ReviewOutputValidationError
from manim_quality.logic._review_output import bind_review_output
from manim_quality.logic.reviewer import LogicReviewer, LogicReviewError
from manim_quality.revisions.fingerprint import evidence_hash



def test_reviewer_rejects_missing_and_outside_workspace_paths(tmp_path: Path) -> None:
    candidate, manifest, evidence = setup_evidence(tmp_path)
    backend = PayloadBackend(issue_payload())
    reviewer_service = service(backend)

    with pytest.raises(LogicReviewError, match="candidate_path cannot be resolved"):
        reviewer_service.review(
            run_id="review-missing",
            evidence=evidence,
            workspace=tmp_path,
            candidate_path=tmp_path / "missing.py",
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    outside.write_text(CODE, encoding="utf-8")
    with pytest.raises(LogicReviewError, match="inside the task workspace"):
        reviewer_service.review(
            run_id="review-outside",
            evidence=evidence,
            workspace=tmp_path,
            candidate_path=outside,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

    assert candidate.is_file()
    assert backend.requests == []

def test_reviewer_reverifies_directly_constructed_engine_evidence(
    tmp_path: Path,
) -> None:
    candidate, manifest, evidence = setup_evidence(tmp_path)
    forged_engine = dict(evidence.engine_evidence)
    forged_engine["visible_math_claims"] = [
        {
            "line": 5,
            "value": "x=999",
            "score": 10,
            "source": "scene_string_literal",
        }
    ]
    forged = replace(evidence, engine_evidence=forged_engine)
    backend = PayloadBackend(
        {
            "decision": "pass",
            "blocked": False,
            "requires_human_review": False,
            "summary": "clean",
            "issues": [],
            "review_gaps": [],
        }
    )

    with pytest.raises(LogicReviewError, match="engine evidence"):
        service(backend).review(
            run_id="review-forged-evidence",
            evidence=forged,
            workspace=tmp_path,
            candidate_path=candidate,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

    assert backend.requests == []
