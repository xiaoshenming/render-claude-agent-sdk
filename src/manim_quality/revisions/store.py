"""Persistence port and immutable job snapshot for quality revisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from manim_quality.contracts import QualityResult, QualityState, Revision
from manim_quality.contracts._formats import require_optional_sha256, require_sha256

from .fence import CommitFence


class Checkpoint(StrEnum):
    RENDER_BASELINE = "render_baseline_revision_id"
    LOGIC_CERTIFIED = "logic_certified_revision_id"
    LAYOUT_CERTIFIED = "layout_certified_revision_id"
    DELIVERY = "delivery_revision_id"


@dataclass(frozen=True, slots=True)
class QualityJobSnapshot:
    job_id: str
    version: int
    state: QualityState
    render_baseline_revision_id: str
    logic_certified_revision_id: str | None
    layout_certified_revision_id: str | None
    delivery_revision_id: str | None
    render_baseline_evidence_hash: str | None = None
    logic_certified_evidence_hash: str | None = None
    layout_certified_evidence_hash: str | None = None
    delivery_evidence_hash: str | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.job_id, "job_id")
        if isinstance(self.version, bool) or not isinstance(self.version, int):
            raise TypeError("version must be an integer")
        if self.version < 0:
            raise ValueError("version must be non-negative")
        if not isinstance(self.state, QualityState):
            raise TypeError("state must be a QualityState")
        _require_identifier(
            self.render_baseline_revision_id, "render_baseline_revision_id"
        )
        for field_name in (
            "logic_certified_revision_id",
            "layout_certified_revision_id",
            "delivery_revision_id",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_identifier(value, field_name)
        for field_name in (
            "render_baseline_evidence_hash",
            "logic_certified_evidence_hash",
            "layout_certified_evidence_hash",
            "delivery_evidence_hash",
        ):
            require_optional_sha256(getattr(self, field_name), field_name)


class RepositoryError(RuntimeError):
    """Base class for revision persistence failures."""


class JobNotFound(RepositoryError):
    pass


class RevisionNotFound(RepositoryError):
    pass


class JobConflict(RepositoryError):
    pass


class RevisionConflict(RepositoryError):
    pass


class ParentRevisionError(RepositoryError):
    pass


class RevisionJobMismatch(RepositoryError):
    pass


class CheckpointConflict(RepositoryError):
    pass


class CheckpointOrderError(RepositoryError):
    pass


class StaleWrite(RepositoryError):
    def __init__(self, job_id: str, expected: int, actual: int) -> None:
        self.job_id = job_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"stale write for {job_id}: expected version {expected}, actual {actual}"
        )


class RepositoryTransactionError(RepositoryError):
    pass


class CommitFenceRejected(RepositoryError):
    pass


class DuplicateRunConflict(RepositoryError):
    pass


class TransitionReplayAdvanced(RepositoryError):
    pass


@dataclass(frozen=True, slots=True)
class TransitionEvidence:
    run_id: str
    reason_code: str
    evidence_hash: str

    def __post_init__(self) -> None:
        _require_identifier(self.run_id, "run_id")
        _require_identifier(self.reason_code, "reason_code")
        require_sha256(self.evidence_hash, "evidence_hash")


@dataclass(frozen=True, slots=True)
class TransitionRecord:
    run_id: str
    reason_code: str
    evidence_hash: str
    source: QualityState
    target: QualityState
    job_version: int


@dataclass(frozen=True, slots=True)
class RollbackRecord:
    job_id: str
    run_id: str
    rollback_to_revision_id: str
    failed_revision_id: str | None
    reason_code: str
    evidence_hash: str
    job_version: int


@runtime_checkable
class RevisionRepository(Protocol):
    def create_job(self, job_id: str, baseline: Revision) -> QualityJobSnapshot: ...

    def append_revision(
        self,
        job_id: str,
        revision: Revision,
        *,
        expected_version: int,
    ) -> QualityJobSnapshot: ...

    def promote_checkpoint(
        self,
        job_id: str,
        checkpoint: Checkpoint,
        revision_id: str,
        *,
        evidence_hash: str,
        expected_version: int,
    ) -> QualityJobSnapshot: ...

    def get_job(self, job_id: str) -> QualityJobSnapshot: ...

    def get_revision(self, revision_id: str) -> Revision: ...

    def begin_run(self, job_id: str, run_id: str, request_hash: str) -> None: ...

    def get_run_result(
        self, job_id: str, run_id: str, request_hash: str
    ) -> QualityResult | None: ...

    def save_run_result(
        self, job_id: str, run_id: str, request_hash: str, result: QualityResult
    ) -> None: ...

    def transition_state(
        self,
        job_id: str,
        source: QualityState,
        target: QualityState,
        evidence: TransitionEvidence,
        *,
        expected_version: int,
    ) -> QualityJobSnapshot: ...

    def certify_checkpoint_state(
        self,
        job_id: str,
        checkpoint: Checkpoint,
        revision_id: str,
        target: QualityState,
        evidence: TransitionEvidence,
        *,
        expected_version: int,
    ) -> QualityJobSnapshot: ...

    def finalize_delivery(
        self,
        job_id: str,
        revision_id: str,
        target: QualityState,
        evidence: TransitionEvidence,
        certificate_payload: bytes,
        result: QualityResult,
        *,
        run_id: str,
        request_hash: str,
        expected_version: int,
        commit_fence: CommitFence | None = None,
    ) -> QualityJobSnapshot: ...

    def finalize_hold(
        self,
        job_id: str,
        rollback_to_revision_id: str,
        failed_revision_id: str | None,
        evidence: TransitionEvidence,
        evidence_payload: bytes,
        result: QualityResult,
        *,
        run_id: str,
        request_hash: str,
        expected_version: int,
        commit_fence: CommitFence | None = None,
    ) -> QualityJobSnapshot: ...

    def list_transitions(self, job_id: str) -> tuple[TransitionRecord, ...]: ...

    def list_rollbacks(self, job_id: str) -> tuple[RollbackRecord, ...]: ...


def _require_identifier(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value


def require_expected_version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("expected_version must be an integer")
    if value < 0:
        raise ValueError("expected_version must be non-negative")
    return value


def require_evidence_hash(value: object) -> str:
    return require_sha256(value, "evidence_hash")
