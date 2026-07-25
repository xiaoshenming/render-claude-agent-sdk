from manim_quality.logic.reporting import (
    review_report_from_dict,
    review_report_to_dict,
)
from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicDecision,
    LogicIssue,
    LogicReviewReport,
)
from manim_quality.revisions.fingerprint import sha256_text

HASH = sha256_text("candidate")


def test_review_report_round_trips_through_persisted_json_shape() -> None:
    issue = LogicIssue(
        "I-1",
        "answer_mismatch",
        IssueSeverity.HIGH,
        0.95,
        True,
        "change the cited Scene expression",
        ("Demo",),
        (
            EvidenceCitation(
                CitationArtifact.CANDIDATE_CODE,
                "candidate.py",
                HASH,
                'MathTex("12")',
                "Demo",
                4,
                4,
            ),
            EvidenceCitation(
                CitationArtifact.PROBLEM_TEXT,
                "problem.txt",
                sha256_text("answer 10"),
                "answer 10",
            ),
        ),
        "display 10",
        "display 12",
        ({"kind": "text_present", "value": "10", "scene_id": "Demo"},),
        ("layout",),
    )
    report = LogicReviewReport(
        "review-1",
        "revision-1",
        HASH,
        sha256_text("manifest"),
        LogicDecision.NEEDS_REPAIR,
        True,
        False,
        "one repairable issue",
        (issue,),
        (),
    )

    restored = review_report_from_dict(review_report_to_dict(report))

    assert restored == report


def test_review_report_parser_rejects_unknown_fields() -> None:
    payload = {
        "review_id": "review-1",
        "revision_id": "revision-1",
        "code_hash": HASH,
        "render_manifest_hash": sha256_text("manifest"),
        "decision": "pass",
        "blocked": False,
        "requires_human_review": False,
        "summary": "clean",
        "issues": [],
        "review_gaps": [],
        "unexpected": True,
    }

    try:
        review_report_from_dict(payload)
    except ValueError as error:
        assert "fields" in str(error)
    else:
        raise AssertionError("unknown fields must be rejected")
