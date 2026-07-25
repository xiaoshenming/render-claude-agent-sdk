"""Parse SDK review output into immutable platform findings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum

from manim_quality.contracts._validation import require_non_empty_string

from ._citation_binding import bind_citation
from ._errors import ReviewBindingInvariantError, ReviewOutputValidationError
from .evidence import LogicEvidence
from .schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicDecision,
    LogicIssue,
    LogicReviewReport,
)

_REPORT_FIELDS = frozenset(
    {"decision", "blocked", "requires_human_review", "summary", "issues", "review_gaps"}
)
_ISSUE_FIELDS = frozenset(
    {
        "issue_id",
        "issue_type",
        "severity",
        "confidence",
        "repairable",
        "repair_scope",
        "target_scene_ids",
        "candidate_evidence",
        "expected_evidence",
        "supporting_evidence",
        "expected",
        "observed",
        "acceptance_predicates",
        "non_goals",
    }
)


def bind_review_output(
    payload: Mapping[str, object],
    *,
    review_id: str,
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> LogicReviewReport:
    _validate_platform_inputs(review_id, evidence, candidate_code, render_manifest_text)
    return _bind_review_output(
        payload,
        review_id=review_id,
        evidence=evidence,
        candidate_code=candidate_code,
        render_manifest_text=render_manifest_text,
    )


def _bind_review_output(
    payload: Mapping[str, object],
    *,
    review_id: str,
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> LogicReviewReport:
    data = _exact_object(payload, _REPORT_FIELDS, "review output")
    issues = tuple(
        _parse_issue(item, evidence, candidate_code, render_manifest_text)
        for item in _array(data["issues"], "issues")
    )
    gaps = tuple(
        _text(item, "review_gaps item")
        for item in _array(data["review_gaps"], "review_gaps")
    )
    try:
        return LogicReviewReport(
            review_id=review_id,
            revision_id=evidence.revision_id,
            code_hash=evidence.code_hash,
            render_manifest_hash=evidence.render_manifest_hash,
            decision=_enum(LogicDecision, data["decision"], "decision"),
            blocked=_bool(data["blocked"], "blocked"),
            requires_human_review=_bool(
                data["requires_human_review"], "requires_human_review"
            ),
            summary=_text(data["summary"], "summary"),
            issues=issues,
            review_gaps=gaps,
        )
    except (TypeError, ValueError) as error:
        raise ReviewOutputValidationError(str(error)) from error


def _validate_platform_inputs(
    review_id: str,
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> None:
    try:
        require_non_empty_string(review_id, "review_id")
    except (TypeError, ValueError) as error:
        raise ReviewBindingInvariantError(str(error)) from error
    if not isinstance(evidence, LogicEvidence):
        raise ReviewBindingInvariantError("evidence must be LogicEvidence")
    if not isinstance(evidence.planning.value, Mapping):
        raise ReviewBindingInvariantError("planning evidence must be an object")
    if type(candidate_code) is not str or type(render_manifest_text) is not str:
        raise ReviewBindingInvariantError("review source artifacts must be text")


def _parse_issue(
    value: object,
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> LogicIssue:
    data = _exact_object(value, _ISSUE_FIELDS, "issue")
    target_scene_ids = tuple(
        _text(item, "target_scene_ids item")
        for item in _array(data["target_scene_ids"], "target_scene_ids")
    )
    known_scenes = {scene.scene_id for scene in evidence.scenes}
    unknown = sorted(set(target_scene_ids) - known_scenes)
    if unknown:
        raise ReviewOutputValidationError(
            f"issue references unknown Scene(s): {', '.join(unknown)}"
        )
    citations = _issue_citations(data, evidence, candidate_code, render_manifest_text)
    if any(
        item.scene_id is not None and item.scene_id not in target_scene_ids
        for item in citations
    ):
        raise ReviewOutputValidationError(
            "citation Scene must be included in target_scene_ids"
        )
    predicates = tuple(
        _json_object(item, "acceptance predicate")
        for item in _array(data["acceptance_predicates"], "acceptance_predicates")
    )
    try:
        return LogicIssue(
            issue_id=_text(data["issue_id"], "issue_id"),
            issue_type=_text(data["issue_type"], "issue_type"),
            severity=_enum(IssueSeverity, data["severity"], "severity"),
            confidence=_number(data["confidence"], "confidence"),
            repairable=_bool(data["repairable"], "repairable"),
            repair_scope=_text(data["repair_scope"], "repair_scope"),
            target_scene_ids=target_scene_ids,
            evidence=citations,
            expected=_string(data["expected"], "expected"),
            observed=_string(data["observed"], "observed"),
            acceptance_predicates=predicates,
            non_goals=tuple(
                _text(item, "non_goals item")
                for item in _array(data["non_goals"], "non_goals")
            ),
        )
    except (TypeError, ValueError) as error:
        raise ReviewOutputValidationError(str(error)) from error


def _parse_citations(
    value: object,
    name: str,
    allowed: frozenset[CitationArtifact] | None,
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> tuple[EvidenceCitation, ...]:
    citations = tuple(
        bind_citation(item, evidence, candidate_code, render_manifest_text)
        for item in _array(value, name)
    )
    if allowed is not None and any(item.artifact not in allowed for item in citations):
        raise ReviewOutputValidationError(f"{name} contains an invalid artifact")
    return citations


def _issue_citations(
    data: Mapping[str, object],
    evidence: LogicEvidence,
    candidate_code: str,
    render_manifest_text: str,
) -> tuple[EvidenceCitation, ...]:
    groups = (
        (
            "candidate_evidence",
            frozenset({CitationArtifact.CANDIDATE_CODE}),
        ),
        (
            "expected_evidence",
            frozenset(
                {
                    CitationArtifact.PROBLEM_TEXT,
                    CitationArtifact.PLANNING,
                    CitationArtifact.EXPECTED_ANSWER,
                }
            ),
        ),
        ("supporting_evidence", None),
    )
    return tuple(
        citation
        for name, allowed in groups
        for citation in _parse_citations(
            data[name],
            name,
            allowed,
            evidence,
            candidate_code,
            render_manifest_text,
        )
    )


def _exact_object(
    value: object, fields: frozenset[str], name: str
) -> Mapping[str, object]:
    data = _json_object(value, name)
    if data.keys() != fields:
        raise ReviewOutputValidationError(f"{name} fields do not match schema")
    return data


def _json_object(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        raise ReviewOutputValidationError(f"{name} must be an object with string keys")
    return value


def _array(value: object, name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ReviewOutputValidationError(f"{name} must be an array")
    return value


def _text(value: object, name: str) -> str:
    try:
        return require_non_empty_string(value, name)
    except (TypeError, ValueError) as error:
        raise ReviewOutputValidationError(str(error)) from error


def _string(value: object, name: str) -> str:
    if type(value) is not str:
        raise ReviewOutputValidationError(f"{name} must be a string")
    return value


def _bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise ReviewOutputValidationError(f"{name} must be bool")
    return value


def _number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReviewOutputValidationError(f"{name} must be a number")
    return float(value)


def _enum(enum_type: type[StrEnum], value: object, name: str) -> StrEnum:
    if type(value) is not str:
        raise ReviewOutputValidationError(f"{name} must be a string")
    try:
        return enum_type(value)
    except ValueError as error:
        raise ReviewOutputValidationError(
            f"{name} has invalid value {value!r}"
        ) from error
