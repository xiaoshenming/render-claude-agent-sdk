"""Bind model terminal output to audited QualitySession state."""

from collections.abc import Mapping

from manim_quality.agents._runtime_models import CorrectableOutputError

from .session import QualitySession


def _output_validator(session: QualitySession):
    def validate(value: Mapping[str, object]) -> None:
        try:
            _bind_output(value, session)
        except (TypeError, ValueError) as error:
            raise CorrectableOutputError(str(error)) from error

    return validate


def _bind_output(value: Mapping[str, object], session: QualitySession) -> str:
    status = value.get("status")
    if status == "submitted":
        return _bind_submitted_output(value, session)
    if status == "held":
        return _bind_held_output(value, session)
    raise ValueError("invalid Quality Operator terminal output")


def _bind_submitted_output(
    value: Mapping[str, object], session: QualitySession
) -> str:
    required = {
        "status", "submitted_revision_id", "code_hash", "problem_hash", "summary",
    }
    keys = set(value)
    if not required <= keys or keys - required > {"hold_reason"}:
        raise ValueError("invalid Quality Operator terminal output")
    submitted = session.submitted_revision_id
    if submitted is None:
        raise ValueError("submit_revision tool must run before terminal output")
    revision = session.get_revision(submitted)
    expected = (submitted, revision.code_hash, session.problem_hash)
    actual = (
        value.get("submitted_revision_id"),
        value.get("code_hash"),
        value.get("problem_hash"),
    )
    if actual != expected:
        raise ValueError("terminal output does not bind submitted revision")
    return _bounded_summary(value)


def _bind_held_output(value: Mapping[str, object], session: QualitySession) -> str:
    allowed = {
        "status", "summary", "hold_reason", "submitted_revision_id",
        "code_hash", "problem_hash",
    }
    if not set(value) <= allowed:
        raise ValueError("held output contains unknown fields")
    if session.submitted_revision_id is not None:
        raise ValueError("held output is forbidden after a real submission")
    reason = value.get("hold_reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 500:
        raise ValueError("hold_reason must be a bounded non-empty string")
    return _bounded_summary(value)


def _bounded_summary(value: Mapping[str, object]) -> str:
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 2_000:
        raise ValueError("summary must be a bounded non-empty string")
    return summary
