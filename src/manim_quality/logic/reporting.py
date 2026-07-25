"""JSON serialization for provenance-bound logic review reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from manim_quality.contracts._json_values import thaw_json_object

from .schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicDecision,
    LogicIssue,
    LogicReviewReport,
)

_REPORT_FIELDS = {
    "review_id",
    "revision_id",
    "code_hash",
    "render_manifest_hash",
    "decision",
    "blocked",
    "requires_human_review",
    "summary",
    "issues",
    "review_gaps",
}
_ISSUE_FIELDS = {
    "issue_id",
    "issue_type",
    "severity",
    "confidence",
    "repairable",
    "repair_scope",
    "target_scene_ids",
    "evidence",
    "expected",
    "observed",
    "acceptance_predicates",
    "non_goals",
}
_CITATION_FIELDS = {
    "artifact",
    "source_ref",
    "source_hash",
    "excerpt",
    "scene_id",
    "line_start",
    "line_end",
}


def review_report_to_dict(report: LogicReviewReport) -> dict[str, object]:
    return {
        "review_id": report.review_id,
        "revision_id": report.revision_id,
        "code_hash": report.code_hash,
        "render_manifest_hash": report.render_manifest_hash,
        "decision": report.decision.value,
        "blocked": report.blocked,
        "requires_human_review": report.requires_human_review,
        "summary": report.summary,
        "issues": [_issue_to_dict(issue) for issue in report.issues],
        "review_gaps": list(report.review_gaps),
    }


def review_report_from_dict(value: Mapping[str, object]) -> LogicReviewReport:
    data = _object(value, "review report", _REPORT_FIELDS)
    return LogicReviewReport(
        review_id=_text(data["review_id"], "review_id"),
        revision_id=_text(data["revision_id"], "revision_id"),
        code_hash=_text(data["code_hash"], "code_hash"),
        render_manifest_hash=_text(
            data["render_manifest_hash"], "render_manifest_hash"
        ),
        decision=LogicDecision(data["decision"]),
        blocked=_bool(data["blocked"], "blocked"),
        requires_human_review=_bool(
            data["requires_human_review"], "requires_human_review"
        ),
        summary=_text(data["summary"], "summary"),
        issues=tuple(_issue(item) for item in _array(data["issues"], "issues")),
        review_gaps=_strings(data["review_gaps"], "review_gaps"),
    )


def _issue_to_dict(issue: LogicIssue) -> dict[str, object]:
    return {
        "issue_id": issue.issue_id,
        "issue_type": issue.issue_type,
        "severity": issue.severity.value,
        "confidence": issue.confidence,
        "repairable": issue.repairable,
        "repair_scope": issue.repair_scope,
        "target_scene_ids": list(issue.target_scene_ids),
        "evidence": [_citation_to_dict(item) for item in issue.evidence],
        "expected": issue.expected,
        "observed": issue.observed,
        "acceptance_predicates": [
            thaw_json_object(item) for item in issue.acceptance_predicates
        ],
        "non_goals": list(issue.non_goals),
    }


def _citation_to_dict(citation: EvidenceCitation) -> dict[str, object]:
    return {
        "artifact": citation.artifact.value,
        "source_ref": citation.source_ref,
        "source_hash": citation.source_hash,
        "excerpt": citation.excerpt,
        "scene_id": citation.scene_id,
        "line_start": citation.line_start,
        "line_end": citation.line_end,
    }


def _issue(value: object) -> LogicIssue:
    data = _object(value, "issue", _ISSUE_FIELDS)
    predicates = _array(data["acceptance_predicates"], "acceptance_predicates")
    return LogicIssue(
        issue_id=_text(data["issue_id"], "issue_id"),
        issue_type=_text(data["issue_type"], "issue_type"),
        severity=IssueSeverity(data["severity"]),
        confidence=_number(data["confidence"], "confidence"),
        repairable=_bool(data["repairable"], "repairable"),
        repair_scope=_text(data["repair_scope"], "repair_scope"),
        target_scene_ids=_strings(data["target_scene_ids"], "target_scene_ids"),
        evidence=tuple(
            _citation(item) for item in _array(data["evidence"], "evidence")
        ),
        expected=_text(data["expected"], "expected"),
        observed=_text(data["observed"], "observed"),
        acceptance_predicates=tuple(
            _object(item, "acceptance predicate") for item in predicates
        ),
        non_goals=_strings(data["non_goals"], "non_goals"),
    )


def _citation(value: object) -> EvidenceCitation:
    data = _object(value, "citation", _CITATION_FIELDS)
    return EvidenceCitation(
        artifact=CitationArtifact(data["artifact"]),
        source_ref=_text(data["source_ref"], "source_ref"),
        source_hash=_text(data["source_hash"], "source_hash"),
        excerpt=_text(data["excerpt"], "excerpt"),
        scene_id=_optional_text(data["scene_id"], "scene_id"),
        line_start=_optional_int(data["line_start"], "line_start"),
        line_end=_optional_int(data["line_end"], "line_end"),
    )


def _object(value: object, name: str, fields=None) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    data = dict(value)
    if fields is not None and set(data) != fields:
        raise ValueError(f"{name} fields do not match schema")
    return data


def _array(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be an array")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _optional_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    return value


def _bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise TypeError(f"{name} must be bool")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    return float(value)


def _strings(value: object, name: str) -> tuple[str, ...]:
    return tuple(_text(item, f"{name} item") for item in _array(value, name))
