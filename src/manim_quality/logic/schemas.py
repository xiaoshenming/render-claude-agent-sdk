"""Immutable logic review findings and decision semantics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from manim_quality.contracts._formats import require_sha256
from manim_quality.contracts._json_values import freeze_json_object
from manim_quality.contracts._validation import (
    freeze_identifier_sequence,
    freeze_string_sequence,
    require_non_empty_string,
)


class LogicDecision(StrEnum):
    PASS = "pass"
    NEEDS_REPAIR = "needs_repair"
    RECORD_ONLY = "record_only"
    HUMAN_REVIEW = "human_review"


class IssueSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CitationArtifact(StrEnum):
    CANDIDATE_CODE = "candidate_code"
    PROBLEM_TEXT = "problem_text"
    PLANNING = "planning"
    EXPECTED_ANSWER = "expected_answer"
    RENDER_MANIFEST = "render_manifest"


_EXPECTED_CLAIM_SOURCES = frozenset(
    {
        CitationArtifact.PROBLEM_TEXT,
        CitationArtifact.PLANNING,
        CitationArtifact.EXPECTED_ANSWER,
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceCitation:
    artifact: CitationArtifact
    source_ref: str
    source_hash: str
    excerpt: str
    scene_id: str | None = None
    line_start: int | None = None
    line_end: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, CitationArtifact):
            raise TypeError("artifact must be CitationArtifact")
        require_non_empty_string(self.source_ref, "source_ref")
        require_sha256(self.source_hash, "source_hash")
        require_non_empty_string(self.excerpt, "excerpt")
        if self.artifact is CitationArtifact.CANDIDATE_CODE:
            _validate_code_location(self.scene_id, self.line_start, self.line_end)
        elif any(
            value is not None
            for value in (self.scene_id, self.line_start, self.line_end)
        ):
            raise ValueError("non-code citations cannot declare code locations")


@dataclass(frozen=True, slots=True)
class LogicIssue:
    issue_id: str
    issue_type: str
    severity: IssueSeverity
    confidence: float
    repairable: bool
    repair_scope: str
    target_scene_ids: Sequence[str]
    evidence: Sequence[EvidenceCitation]
    expected: str
    observed: str
    acceptance_predicates: Sequence[Mapping[str, object]]
    non_goals: Sequence[str]

    def __post_init__(self) -> None:
        _validate_issue_fields(self)
        scene_ids = freeze_identifier_sequence(
            self.target_scene_ids, "target_scene_ids"
        )
        if not scene_ids:
            raise ValueError("target_scene_ids must not be empty")
        object.__setattr__(self, "target_scene_ids", scene_ids)
        object.__setattr__(self, "evidence", _freeze_issue_citations(self.evidence))
        expected = require_non_empty_string(self.expected, "expected")
        observed = require_non_empty_string(self.observed, "observed")
        if _normalized_claim(expected) == _normalized_claim(observed):
            raise ValueError("issue expected and observed claims must conflict")
        object.__setattr__(
            self,
            "acceptance_predicates",
            _freeze_acceptance_predicates(
                self.acceptance_predicates, repairable=self.repairable
            ),
        )
        object.__setattr__(
            self, "non_goals", freeze_string_sequence(self.non_goals, "non_goals")
        )


@dataclass(frozen=True, slots=True)
class LogicReviewReport:
    review_id: str
    revision_id: str
    code_hash: str
    render_manifest_hash: str
    decision: LogicDecision
    blocked: bool
    requires_human_review: bool
    summary: str
    issues: Sequence[LogicIssue]
    review_gaps: Sequence[str]

    def __post_init__(self) -> None:
        require_non_empty_string(self.review_id, "review_id")
        require_non_empty_string(self.revision_id, "revision_id")
        require_sha256(self.code_hash, "code_hash")
        require_sha256(self.render_manifest_hash, "render_manifest_hash")
        if not isinstance(self.decision, LogicDecision):
            raise TypeError("decision must be LogicDecision")
        if not isinstance(self.blocked, bool) or not isinstance(
            self.requires_human_review, bool
        ):
            raise TypeError("review flags must be bool")
        require_non_empty_string(self.summary, "summary")
        issues = tuple(self.issues)
        if not all(isinstance(item, LogicIssue) for item in issues):
            raise TypeError("issues must contain LogicIssue values")
        if len({item.issue_id for item in issues}) != len(issues):
            raise ValueError("issue_id values must be unique")
        object.__setattr__(self, "issues", issues)
        gaps = freeze_string_sequence(self.review_gaps, "review_gaps")
        object.__setattr__(self, "review_gaps", gaps)
        _validate_decision(self)


def _validate_code_location(
    scene_id: str | None, line_start: int | None, line_end: int | None
) -> None:
    if scene_id is not None:
        require_non_empty_string(scene_id, "scene_id")
    if type(line_start) is not int or type(line_end) is not int:
        raise TypeError("code citations require integer line bounds")
    if line_start < 1 or line_end < line_start:
        raise ValueError("code citation line bounds are invalid")


def _normalized_claim(value: str) -> str:
    return " ".join(value.split()).casefold()


def _validate_issue_fields(issue: LogicIssue) -> None:
    require_non_empty_string(issue.issue_id, "issue_id")
    require_non_empty_string(issue.issue_type, "issue_type")
    if not isinstance(issue.severity, IssueSeverity):
        raise TypeError("severity must be IssueSeverity")
    if isinstance(issue.confidence, bool) or not isinstance(
        issue.confidence, (int, float)
    ):
        raise TypeError("confidence must be a number")
    if not 0 <= issue.confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(issue.repairable, bool):
        raise TypeError("repairable must be bool")
    require_non_empty_string(issue.repair_scope, "repair_scope")


def _freeze_issue_citations(
    evidence: Sequence[EvidenceCitation],
) -> tuple[EvidenceCitation, ...]:
    citations = tuple(evidence)
    if not citations or not all(
        isinstance(item, EvidenceCitation) for item in citations
    ):
        raise ValueError("evidence must contain direct citations")
    if not any(item.artifact is CitationArtifact.CANDIDATE_CODE for item in citations):
        raise ValueError("every issue requires candidate code evidence")
    if not any(item.artifact in _EXPECTED_CLAIM_SOURCES for item in citations):
        raise ValueError("every issue requires an expected claim source")
    return citations


def _freeze_acceptance_predicates(
    values: Sequence[Mapping[str, object]], *, repairable: bool
) -> tuple[Mapping[str, object], ...]:
    predicates = tuple(
        freeze_json_object(item, f"acceptance_predicates[{index}]")
        for index, item in enumerate(values)
    )
    if repairable and not predicates:
        raise ValueError("repairable issue requires an acceptance predicate")
    return predicates


def _validate_decision(report: LogicReviewReport) -> None:
    validators = {
        LogicDecision.PASS: _validate_pass,
        LogicDecision.NEEDS_REPAIR: _validate_needs_repair,
        LogicDecision.RECORD_ONLY: _validate_record_only,
        LogicDecision.HUMAN_REVIEW: _validate_human_review,
    }
    validators[report.decision](report)


def _validate_pass(report: LogicReviewReport) -> None:
    if (
        report.blocked
        or report.requires_human_review
        or report.issues
        or report.review_gaps
    ):
        raise ValueError("PASS cannot contain blockers, issues, or review gaps")


def _validate_needs_repair(report: LogicReviewReport) -> None:
    if not report.blocked or report.requires_human_review or not report.issues:
        raise ValueError("NEEDS_REPAIR requires blocking repair issues")
    if report.review_gaps:
        raise ValueError("NEEDS_REPAIR cannot contain unresolved review gaps")
    if not all(issue.repairable for issue in report.issues):
        raise ValueError("NEEDS_REPAIR requires every issue to be repairable")


def _validate_record_only(report: LogicReviewReport) -> None:
    if (
        report.blocked
        or report.requires_human_review
        or not report.issues
        or report.review_gaps
    ):
        raise ValueError("RECORD_ONLY requires only non-blocking issues")


def _validate_human_review(report: LogicReviewReport) -> None:
    if not report.blocked or not report.requires_human_review:
        raise ValueError("HUMAN_REVIEW must block automatic progress")
    if not report.issues and not report.review_gaps:
        raise ValueError("HUMAN_REVIEW requires an issue or review gap")
