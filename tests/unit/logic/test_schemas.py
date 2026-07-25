from dataclasses import replace

import pytest

from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicDecision,
    LogicIssue,
    LogicReviewReport,
)

HASH = "sha256:" + "a" * 64


def citation() -> EvidenceCitation:
    return EvidenceCitation(
        artifact=CitationArtifact.CANDIDATE_CODE,
        source_ref="artifacts/candidate.py",
        source_hash=HASH,
        excerpt='MathTex("x=12")',
        scene_id="Scene_02",
        line_start=10,
        line_end=10,
    )


def expected_source_citation() -> EvidenceCitation:
    return EvidenceCitation(
        artifact=CitationArtifact.EXPECTED_ANSWER,
        source_ref="submission:expected_answer",
        source_hash=HASH,
        excerpt="x=10",
    )


def issue() -> LogicIssue:
    return LogicIssue(
        issue_id="issue-1",
        issue_type="final_answer_mismatch",
        severity=IssueSeverity.HIGH,
        confidence=0.95,
        repairable=True,
        repair_scope="scene_logic",
        target_scene_ids=("Scene_02",),
        evidence=(citation(), expected_source_citation()),
        expected="x=10",
        observed="x=12",
        acceptance_predicates=({"kind": "text_absent", "value": "x=12"},),
        non_goals=("layout",),
    )


def report(**changes: object) -> LogicReviewReport:
    values = {
        "review_id": "review-1",
        "revision_id": "rev-1",
        "code_hash": HASH,
        "render_manifest_hash": HASH,
        "decision": LogicDecision.NEEDS_REPAIR,
        "blocked": True,
        "requires_human_review": False,
        "summary": "发现答案不一致",
        "issues": (issue(),),
        "review_gaps": (),
    }
    values.update(changes)
    return LogicReviewReport(**values)  # type: ignore[arg-type]


def test_report_accepts_consistent_repair_and_pass_states() -> None:
    assert report().decision is LogicDecision.NEEDS_REPAIR
    clean = report(
        decision=LogicDecision.PASS,
        blocked=False,
        issues=(),
        summary="未发现有证据支持的逻辑问题",
    )
    assert clean.issues == ()

    assert (
        report(
            decision=LogicDecision.RECORD_ONLY,
            blocked=False,
            requires_human_review=False,
        ).blocked
        is False
    )
    assert (
        report(
            decision=LogicDecision.HUMAN_REVIEW,
            blocked=True,
            requires_human_review=True,
            issues=(),
            review_gaps=("题目证据不足",),
        ).requires_human_review
        is True
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": LogicDecision.PASS, "blocked": True, "issues": ()},
        {"decision": LogicDecision.PASS, "blocked": False},
        {
            "decision": LogicDecision.HUMAN_REVIEW,
            "blocked": False,
            "requires_human_review": True,
            "issues": (),
            "review_gaps": ("无法验证",),
        },
        {
            "decision": LogicDecision.HUMAN_REVIEW,
            "blocked": True,
            "requires_human_review": False,
            "issues": (),
            "review_gaps": ("无法验证",),
        },
        {"decision": LogicDecision.NEEDS_REPAIR, "blocked": False},
    ],
)
def test_report_rejects_contradictory_pass_blocked_and_human_states(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        report(**changes)


def test_issue_requires_direct_candidate_evidence() -> None:
    with pytest.raises(ValueError, match="candidate code"):
        LogicIssue(
            issue_id="issue-1",
            issue_type="unsupported_claim",
            severity=IssueSeverity.HIGH,
            confidence=0.8,
            repairable=False,
            repair_scope="none",
            target_scene_ids=("Scene_02",),
            evidence=(
                EvidenceCitation(
                    artifact=CitationArtifact.PROBLEM_TEXT,
                    source_ref="submission:problem",
                    source_hash=HASH,
                    excerpt="x=10",
                ),
            ),
            expected="x=10",
            observed="x=12",
            acceptance_predicates=(),
            non_goals=(),
        )


def test_issue_requires_expected_claim_source() -> None:
    with pytest.raises(ValueError, match="expected claim source"):
        replace(issue(), evidence=(citation(),))


@pytest.mark.parametrize(
    "changes",
    [
        {"expected": ""},
        {"observed": ""},
        {"expected": " X = 12 ", "observed": "x = 12"},
        {"acceptance_predicates": ()},
    ],
)
def test_repairable_issue_rejects_incomplete_or_non_conflicting_claims(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        replace(issue(), **changes)


def test_citations_require_consistent_artifact_locations() -> None:
    with pytest.raises(TypeError, match="CitationArtifact"):
        replace(citation(), artifact="candidate_code")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="line bounds"):
        EvidenceCitation(
            artifact=CitationArtifact.CANDIDATE_CODE,
            source_ref="candidate.py",
            source_hash=HASH,
            excerpt="x=12",
        )
    with pytest.raises(ValueError, match="non-code"):
        EvidenceCitation(
            artifact=CitationArtifact.PROBLEM_TEXT,
            source_ref="submission:problem",
            source_hash=HASH,
            excerpt="x=10",
            line_start=1,
            line_end=1,
        )
    with pytest.raises(ValueError, match="line bounds"):
        replace(citation(), line_start=0)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, True])
def test_issue_rejects_invalid_confidence(confidence: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(issue(), confidence=confidence)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"severity": "high"},
        {"repairable": "yes"},
        {"target_scene_ids": ()},
        {"evidence": ("not-a-citation",)},
    ],
)
def test_issue_rejects_invalid_contract_types(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(issue(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"decision": "pass"},
        {"blocked": "yes"},
        {"issues": ("not-an-issue",)},
        {"issues": (issue(), issue())},
        {"issues": (replace(issue(), repairable=False),)},
        {"review_gaps": ("unresolved evidence",)},
        {
            "issues": (
                issue(),
                replace(
                    issue(),
                    issue_id="issue-2",
                    repairable=False,
                    severity=IssueSeverity.CRITICAL,
                ),
            )
        },
        {
            "decision": LogicDecision.RECORD_ONLY,
            "blocked": False,
            "issues": (),
        },
        {
            "decision": LogicDecision.HUMAN_REVIEW,
            "blocked": True,
            "requires_human_review": True,
            "issues": (),
            "review_gaps": (),
        },
    ],
)
def test_report_rejects_invalid_contract_values(changes: dict[str, object]) -> None:
    with pytest.raises((TypeError, ValueError)):
        report(**changes)
