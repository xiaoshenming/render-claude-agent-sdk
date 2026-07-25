"""Independent acceptance gate for an Agent-submitted candidate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from .content_guard import content_retention_reasons
from .models import CandidateAttempt, ValidationOutcome
from .ports import LayoutInspector, RevisionValidator
from .session import QualitySession


class GateDecision(StrEnum):
    PROPOSED = "PROPOSED"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class GateResult:
    decision: GateDecision
    final_revision: CandidateAttempt | None
    rollback_revision: CandidateAttempt | None
    reasons: tuple[str, ...]
    validation: ValidationOutcome | None
    layout_report: Mapping[str, object] | None


class OuterAcceptanceGate:
    """Recompute acceptance facts without trusting Agent terminal output."""

    def __init__(
        self,
        *,
        revision_validator: RevisionValidator,
        layout_inspector: LayoutInspector,
    ) -> None:
        self._validator = revision_validator
        self._layout = layout_inspector

    async def evaluate(self, session: QualitySession) -> GateResult:
        if not isinstance(session, QualitySession):
            raise TypeError("session must be QualitySession")
        reasons: list[str] = []
        validation: ValidationOutcome | None = None
        layout_report: Mapping[str, object] | None = None
        submitted = session.submitted_revision_id
        if submitted is None:
            reasons.append("missing_agent_submission")
            return _hold(session, reasons, validation, layout_report)
        candidate = session.get_revision(submitted)
        reasons.extend(_compile_reasons(candidate))
        reasons.extend(content_retention_reasons(session.baseline, candidate))
        validation, validation_reasons = await _validate(
            self._validator,
            candidate,
            session.findings,
            session.problem_hash,
        )
        reasons.extend(validation_reasons)
        layout_report, layout_reasons = await _inspect_layout(
            self._layout,
            candidate,
            session.problem_hash,
        )
        reasons.extend(layout_reasons)
        if reasons:
            return _hold(session, reasons, validation, layout_report)
        return GateResult(
            decision=GateDecision.PROPOSED,
            final_revision=candidate,
            rollback_revision=None,
            reasons=(),
            validation=validation,
            layout_report=layout_report,
        )


def _compile_reasons(candidate: CandidateAttempt) -> tuple[str, ...]:
    try:
        compile(candidate.code, "candidate.py", "exec")
    except SyntaxError:
        return ("candidate_compile_failed",)
    return ()


async def _validate(validator, candidate, findings, problem_hash):
    try:
        result = await validator.validate(candidate, findings, problem_hash)
    except Exception:
        return None, ("independent_validation_error",)
    if not isinstance(result, ValidationOutcome):
        return None, ("invalid_validation_result",)
    if (
        result.revision_id,
        result.code_hash,
        result.problem_hash,
    ) != (candidate.revision_id, candidate.code_hash, problem_hash):
        return result, ("validation_identity_mismatch",)
    if not result.passed:
        return result, ("independent_validation_failed",)
    if result.details.get("rendered") is not True:
        return result, ("full_render_not_verified",)
    return result, ()


async def _inspect_layout(inspector, candidate, problem_hash):
    try:
        report = await inspector.inspect(candidate, problem_hash)
    except Exception:
        return None, ("layout_inspection_error",)
    blocking = report.get("blocking_count")
    identity = (
        report.get("revision_id"),
        report.get("code_hash"),
        report.get("problem_hash"),
    )
    if identity != (candidate.revision_id, candidate.code_hash, problem_hash):
        return report, ("layout_identity_mismatch",)
    if type(blocking) is not int or blocking < 0:
        return report, ("invalid_layout_report",)
    if report.get("verified") is not True:
        return report, ("full_layout_not_verified",)
    if blocking > 0:
        return report, ("blocking_overlap_remaining",)
    return report, ()


def _hold(
    session: QualitySession,
    reasons: list[str],
    validation: ValidationOutcome | None,
    layout_report: Mapping[str, object] | None,
) -> GateResult:
    return GateResult(
        decision=GateDecision.HOLD,
        final_revision=None,
        rollback_revision=session.baseline,
        reasons=tuple(reasons),
        validation=validation,
        layout_report=layout_report,
    )
