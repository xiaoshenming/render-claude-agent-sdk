"""Fail-closed result construction for orchestration failures."""

from manim_quality.contracts import DeliveryDecision, QualityResult
from manim_quality.revisions.store import StaleWrite


class StageExecutionError(RuntimeError):
    def __init__(
        self, code: str, message: str, failed_revision_id: str | None = None
    ) -> None:
        self.code = code
        self.failed_revision_id = failed_revision_id
        super().__init__(message)


class HoldPersistenceError(RuntimeError):
    def __init__(self, job_id: str, run_id: str) -> None:
        super().__init__(
            f"failed to persist HOLD for job {job_id} run {run_id} after 2 attempts"
        )


def failure_reason(error: Exception) -> str:
    if isinstance(error, StageExecutionError):
        return f"{error.code}:{error}"
    if isinstance(error, StaleWrite):
        return f"stale_worker:{error}"
    return f"{type(error).__name__}:{error}"


def hold_result(job_id: str, reason: str) -> QualityResult:
    return QualityResult(
        job_id=job_id,
        decision=DeliveryDecision.HOLD,
        accepted_revision_id=None,
        final_code_ref=None,
        final_render_manifest_ref=None,
        certificate_ref=None,
        warnings=(reason,),
        token_usage={},
        timings_ms={},
    )
