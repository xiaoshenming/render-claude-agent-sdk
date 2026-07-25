"""Bounded atomic HOLD and explicit rollback coordination."""

from manim_quality.contracts import QualityState
from manim_quality.delivery.evidence import canonical_bytes, content_hash
from manim_quality.revisions.store import (
    CommitFence,
    RevisionRepository,
    StaleWrite,
    TransitionEvidence,
)

from .failures import (
    HoldPersistenceError,
    StageExecutionError,
    failure_reason,
    hold_result,
)
from .models import ExecutionRequest, OrchestrationResult


class HoldCoordinator:
    def __init__(self, repository: RevisionRepository) -> None:
        self._repository = repository

    def hold(
        self,
        request: ExecutionRequest,
        error: Exception,
        commit_fence: CommitFence | None = None,
    ) -> OrchestrationResult:
        result = hold_result(request.job_id, failure_reason(error))
        for _attempt in range(2):
            snapshot = self._repository.get_job(request.job_id)
            existing = self._repository.get_run_result(
                request.job_id, request.run_id, request.request_hash
            )
            if existing is not None:
                return OrchestrationResult(existing, snapshot)
            rollback_to = rollback_revision(snapshot)
            failed_revision = getattr(error, "failed_revision_id", None)
            reason_code = failure_code(error)
            payload_data = {
                "failed_revision_id": failed_revision,
                "job_id": request.job_id,
                "reason": failure_reason(error),
                "request_hash": request.request_hash,
                "rollback_to_revision_id": rollback_to,
                "run_id": request.run_id,
                "schema_version": 1,
            }
            try:
                held = self._repository.finalize_hold(
                    request.job_id,
                    rollback_to,
                    failed_revision,
                    TransitionEvidence(
                        f"{request.run_id}:rollback",
                        reason_code,
                        content_hash(payload_data),
                    ),
                    canonical_bytes(payload_data),
                    result,
                    run_id=request.run_id,
                    request_hash=request.request_hash,
                    expected_version=snapshot.version,
                    commit_fence=commit_fence,
                )
                return OrchestrationResult(result, held)
            except StaleWrite:
                continue
        raise HoldPersistenceError(request.job_id, request.run_id)


def failure_code(error: Exception) -> str:
    if isinstance(error, StageExecutionError):
        return error.code
    if isinstance(error, StaleWrite):
        return "stale_worker"
    return type(error).__name__


def rollback_revision(snapshot) -> str:
    if (
        snapshot.state
        in {
            QualityState.FINAL_CONSISTENCY_GATE,
            QualityState.LAYOUT_CERTIFIED,
            QualityState.LAYOUT_CERTIFIED_WITH_WARNING,
        }
        and snapshot.layout_certified_revision_id
    ):
        return snapshot.layout_certified_revision_id
    if (
        snapshot.state
        in {
            QualityState.LAYOUT_CHECKING,
            QualityState.LAYOUT_REPAIRING,
            QualityState.LAYOUT_VERIFYING,
            QualityState.LOGIC_CERTIFIED,
            QualityState.LOGIC_CERTIFIED_WITH_WARNING,
        }
        and snapshot.logic_certified_revision_id
    ):
        return snapshot.logic_certified_revision_id
    return snapshot.render_baseline_revision_id
