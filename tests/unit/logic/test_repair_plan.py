from manim_quality.logic._scene_evidence import extract_scenes
from manim_quality.logic.repair_plan import build_repair_plan
from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicDecision,
    LogicIssue,
    LogicReviewReport,
)
from manim_quality.revisions.fingerprint import code_hash, sha256_text

CODE = """from manim import *

class SceneOne(Scene):
    def construct(self):
        self.add(MathTex("x=12"))

class SceneTwo(Scene):
    def construct(self):
        self.add(Text("AB parallel CD"))
"""


def issue(issue_id: str, scene_id: str, observed: str, expected: str) -> LogicIssue:
    lines = CODE.splitlines()
    line = next(index for index, value in enumerate(lines, 1) if observed in value)
    return LogicIssue(
        issue_id=issue_id,
        issue_type="logic_mismatch",
        severity=IssueSeverity.HIGH,
        confidence=0.95,
        repairable=True,
        repair_scope="smallest scene-local semantic correction",
        target_scene_ids=(scene_id,),
        evidence=(
            EvidenceCitation(
                artifact=CitationArtifact.CANDIDATE_CODE,
                source_ref="candidate.py",
                source_hash=code_hash(CODE),
                excerpt=lines[line - 1].strip(),
                scene_id=scene_id,
                line_start=line,
                line_end=line,
            ),
            EvidenceCitation(
                artifact=CitationArtifact.PROBLEM_TEXT,
                source_ref="problem.txt",
                source_hash=sha256_text(expected),
                excerpt=expected,
            ),
        ),
        expected=expected,
        observed=observed,
        acceptance_predicates=({"kind": "text_present", "value": expected},),
        non_goals=("layout",),
    )


def test_plan_freezes_multiple_issues_and_scene_regions() -> None:
    issues = (
        issue("I-1", "SceneOne", "x=12", "x=10"),
        issue("I-2", "SceneTwo", "AB parallel CD", "AB perpendicular CD"),
    )
    report = LogicReviewReport(
        review_id="review-1",
        revision_id="revision-1",
        code_hash=code_hash(CODE),
        render_manifest_hash=sha256_text("render"),
        decision=LogicDecision.NEEDS_REPAIR,
        blocked=True,
        requires_human_review=False,
        summary="Two repairable logic mismatches.",
        issues=issues,
        review_gaps=(),
    )

    plan = build_repair_plan(report, extract_scenes(CODE))

    assert plan.source_code_hash == code_hash(CODE)
    assert plan.issue_ids == ("I-1", "I-2")
    assert plan.target_scene_ids == ("SceneOne", "SceneTwo")
    assert [region.scene_id for region in plan.allowed_edit_regions] == [
        "SceneOne",
        "SceneTwo",
    ]
    assert plan.max_attempts == 2
    assert "layout or overlap changes" in plan.forbidden_changes


def test_plan_rejects_scene_not_present_in_bound_candidate() -> None:
    broken = issue("I-1", "MissingScene", "x=12", "x=10")
    report = LogicReviewReport(
        review_id="review-1",
        revision_id="revision-1",
        code_hash=code_hash(CODE),
        render_manifest_hash=sha256_text("render"),
        decision=LogicDecision.NEEDS_REPAIR,
        blocked=True,
        requires_human_review=False,
        summary="Repairable mismatch.",
        issues=(broken,),
        review_gaps=(),
    )

    try:
        build_repair_plan(report, extract_scenes(CODE))
    except ValueError as error:
        assert "unknown Scene" in str(error)
    else:
        raise AssertionError("unknown Scene must be rejected")


def test_plan_rejects_conflicting_expectations_for_same_code_evidence() -> None:
    first = issue("I-1", "SceneOne", "x=12", "x=10")
    second = issue("I-2", "SceneOne", "x=12", "x=8")
    report = LogicReviewReport(
        review_id="review-1",
        revision_id="revision-1",
        code_hash=code_hash(CODE),
        render_manifest_hash=sha256_text("render"),
        decision=LogicDecision.NEEDS_REPAIR,
        blocked=True,
        requires_human_review=False,
        summary="Conflicting repair claims.",
        issues=(first, second),
        review_gaps=(),
    )

    try:
        build_repair_plan(report, extract_scenes(CODE))
    except ValueError as error:
        assert "conflicting expected claims" in str(error)
    else:
        raise AssertionError("conflicting repair claims must be rejected")
