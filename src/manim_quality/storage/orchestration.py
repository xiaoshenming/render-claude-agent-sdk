"""Atomic SQLite operations for persisted quality orchestration."""

from __future__ import annotations

from manim_quality.contracts import QualityResult, QualityState, require_transition
from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.revisions.store import (
    Checkpoint,
    CommitFence,
    CommitFenceRejected,
    QualityJobSnapshot,
    RollbackRecord,
    TransitionEvidence,
    TransitionRecord,
    require_expected_version,
)

from ._checkpoint_records import record_checkpoint
from ._orchestration_records import SQLiteOrchestrationRecordsMixin
from ._revision_records import snapshot_from_row
from ._rollback_records import list_rollbacks as load_rollbacks
from ._rollback_records import record_rollback
from ._run_records import result_payload
from ._sqlite import transaction


class SQLiteOrchestrationMixin(SQLiteOrchestrationRecordsMixin):
    def transition_state(
        self,
        job_id: str,
        source: QualityState,
        target: QualityState,
        evidence: TransitionEvidence,
        *,
        expected_version: int,
    ) -> QualityJobSnapshot:
        require_expected_version(expected_version)
        require_transition(source, target)
        with transaction(self._connection):
            if self._matching_transition(job_id, source, target, evidence):
                return snapshot_from_row(self._require_job(job_id))
            job = self._require_state_version(job_id, source, expected_version)
            self._update_state(job_id, target, expected_version, int(job["version"]))
            self._record_transition(
                job_id, source, target, evidence, expected_version + 1
            )
            return snapshot_from_row(self._require_job(job_id))

    def certify_checkpoint_state(
        self,
        job_id: str,
        checkpoint: Checkpoint,
        revision_id: str,
        target: QualityState,
        evidence: TransitionEvidence,
        *,
        expected_version: int,
    ) -> QualityJobSnapshot:
        with transaction(self._connection):
            if self._matching_transition(job_id, None, target, evidence):
                return snapshot_from_row(self._require_job(job_id))
            job = self._require_job(job_id)
            source = QualityState(job["state"])
            require_transition(source, target)
            self._require_state_version(job_id, source, expected_version)
            self._require_promotable(job_id, checkpoint, revision_id, job)
            self._update_checkpoint_state(
                job_id,
                checkpoint,
                revision_id,
                target,
                evidence.evidence_hash,
                expected_version,
                int(job["version"]),
            )
            version = expected_version + 1
            record_checkpoint(
                self._connection,
                job_id,
                checkpoint,
                revision_id,
                evidence.evidence_hash,
                version=version,
            )
            self._record_transition(job_id, source, target, evidence, version)
            return snapshot_from_row(self._require_job(job_id))

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
    ) -> QualityJobSnapshot:
        if sha256_bytes(certificate_payload) != evidence.evidence_hash:
            raise ValueError("certificate payload does not match evidence hash")
        with transaction(self._connection):
            self._require_commit_fence(job_id, run_id, commit_fence)
            job = self._require_job(job_id)
            source = QualityState(job["state"])
            require_transition(source, target)
            self._require_state_version(job_id, source, expected_version)
            self._require_promotable(job_id, Checkpoint.DELIVERY, revision_id, job)
            run = self._require_run(job_id, run_id, request_hash)
            if run["result_payload"] is not None:
                raise ValueError("delivery run already has a result")
            self._store_evidence(evidence.evidence_hash, certificate_payload)
            self._update_checkpoint_state(
                job_id,
                Checkpoint.DELIVERY,
                revision_id,
                target,
                evidence.evidence_hash,
                expected_version,
                int(job["version"]),
            )
            version = expected_version + 1
            record_checkpoint(
                self._connection,
                job_id,
                Checkpoint.DELIVERY,
                revision_id,
                evidence.evidence_hash,
                version=version,
            )
            self._record_transition(job_id, source, target, evidence, version)
            self._connection.execute(
                "UPDATE quality_runs SET result_payload = ? "
                "WHERE job_id = ? AND run_id = ?",
                (result_payload(result), job_id, run_id),
            )
            return snapshot_from_row(self._require_job(job_id))

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
    ) -> QualityJobSnapshot:
        if sha256_bytes(evidence_payload) != evidence.evidence_hash:
            raise ValueError("hold evidence payload does not match evidence hash")
        with transaction(self._connection):
            self._require_commit_fence(job_id, run_id, commit_fence)
            job = self._require_job(job_id)
            source = QualityState(job["state"])
            require_transition(source, QualityState.HOLD)
            self._require_state_version(job_id, source, expected_version)
            self._require_run(job_id, run_id, request_hash)
            self._require_owned_revision(job_id, rollback_to_revision_id)
            if failed_revision_id is not None:
                self._require_owned_revision(job_id, failed_revision_id)
            self._store_evidence(evidence.evidence_hash, evidence_payload)
            self._update_state(
                job_id, QualityState.HOLD, expected_version, int(job["version"])
            )
            version = expected_version + 1
            self._record_transition(
                job_id, source, QualityState.HOLD, evidence, version
            )
            record_rollback(
                self._connection,
                job_id,
                run_id,
                rollback_to_revision_id,
                failed_revision_id,
                evidence.reason_code,
                evidence.evidence_hash,
                version,
            )
            self._connection.execute(
                "UPDATE quality_runs SET result_payload = ? "
                "WHERE job_id = ? AND run_id = ?",
                (result_payload(result), job_id, run_id),
            )
            return snapshot_from_row(self._require_job(job_id))

    def _require_commit_fence(
        self,
        job_id: str,
        run_id: str,
        fence: CommitFence | None,
    ) -> None:
        if fence is None:
            return
        if fence.stage_run_id != run_id:
            raise CommitFenceRejected("commit fence does not match orchestration run")
        row = self._connection.execute(
            """
            SELECT 1 FROM quality_queue
            WHERE stage_run_id = ? AND job_id = ? AND queue_class = 'QUALITY'
              AND state = 'RUNNING' AND lease_owner = ? AND lease_token = ?
              AND deadline = ? AND lease_expires_at IS NOT NULL
              AND julianday(deadline) > julianday('now')
              AND julianday(lease_expires_at) > julianday('now')
            """,
            (
                fence.stage_run_id,
                job_id,
                fence.lease_owner,
                fence.lease_token,
                fence.deadline.isoformat(),
            ),
        ).fetchone()
        if row is None:
            raise CommitFenceRejected(f"quality commit fence rejected: {run_id}")

    def list_transitions(self, job_id: str) -> tuple[TransitionRecord, ...]:
        rows = self._connection.execute(
            "SELECT * FROM quality_state_transitions WHERE job_id = ? "
            "ORDER BY job_version",
            (job_id,),
        ).fetchall()
        return tuple(
            TransitionRecord(
                row["run_id"],
                row["reason_code"],
                row["evidence_hash"],
                QualityState(row["source_state"]),
                QualityState(row["target_state"]),
                row["job_version"],
            )
            for row in rows
        )

    def list_rollbacks(self, job_id: str) -> tuple[RollbackRecord, ...]:
        return load_rollbacks(self._connection, job_id)
