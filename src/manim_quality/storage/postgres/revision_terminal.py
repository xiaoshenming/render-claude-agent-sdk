"""Lease-fenced PostgreSQL ACCEPT and HOLD transactions."""

from manim_quality.contracts import QualityState, require_transition
from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.revisions.store import (
    Checkpoint,
    CommitFenceRejected,
    DuplicateRunConflict,
    StaleWrite,
)

from .revision_codec import result_parameter, session, snapshot


class PostgresRevisionTerminalMixin:
    def finalize_delivery(
        self,
        job_id,
        revision_id,
        target,
        evidence,
        certificate_payload,
        result,
        *,
        run_id,
        request_hash,
        expected_version,
        commit_fence=None,
    ):
        if sha256_bytes(certificate_payload) != evidence.evidence_hash:
            raise ValueError("certificate payload does not match evidence hash")
        with session(self._connection_factory, transaction=True) as connection:
            self._lock_commit_fence(connection, job_id, run_id, commit_fence)
            job = self._require_job(connection, job_id)
            source = QualityState(job["state"])
            require_transition(source, target)
            self._require_version(job, job_id, expected_version)
            self._require_promotable(
                connection, job_id, Checkpoint.DELIVERY, revision_id, job
            )
            run = self._require_run(connection, job_id, run_id, request_hash)
            self._require_unfinished_run(run, run_id)
            self._store_evidence(
                connection, evidence.evidence_hash, certificate_payload
            )
            self._update_checkpoint_state(
                connection,
                job_id,
                Checkpoint.DELIVERY,
                revision_id,
                target,
                evidence.evidence_hash,
                expected_version,
                int(job["version"]),
            )
            version = expected_version + 1
            self._record_checkpoint(
                connection,
                job_id,
                Checkpoint.DELIVERY,
                revision_id,
                evidence.evidence_hash,
                version,
            )
            self._record_transition(
                connection, job_id, source, target, evidence, version
            )
            self._save_terminal_result(connection, job_id, run_id, result)
            return snapshot(self._require_job(connection, job_id))

    def finalize_hold(
        self,
        job_id,
        rollback_to_revision_id,
        failed_revision_id,
        evidence,
        evidence_payload,
        result,
        *,
        run_id,
        request_hash,
        expected_version,
        commit_fence=None,
    ):
        if sha256_bytes(evidence_payload) != evidence.evidence_hash:
            raise ValueError("hold evidence payload does not match evidence hash")
        with session(self._connection_factory, transaction=True) as connection:
            self._lock_commit_fence(connection, job_id, run_id, commit_fence)
            job = self._require_job(connection, job_id)
            source = QualityState(job["state"])
            require_transition(source, QualityState.HOLD)
            self._require_version(job, job_id, expected_version)
            run = self._require_run(connection, job_id, run_id, request_hash)
            self._require_unfinished_run(run, run_id)
            self._require_owned_revision(connection, job_id, rollback_to_revision_id)
            if failed_revision_id is not None:
                self._require_owned_revision(connection, job_id, failed_revision_id)
            self._store_evidence(connection, evidence.evidence_hash, evidence_payload)
            self._update_state(
                connection,
                job_id,
                QualityState.HOLD,
                expected_version,
                int(job["version"]),
            )
            version = expected_version + 1
            self._record_transition(
                connection, job_id, source, QualityState.HOLD, evidence, version
            )
            self._record_rollback(
                connection,
                job_id,
                run_id,
                rollback_to_revision_id,
                failed_revision_id,
                evidence,
                version,
            )
            self._save_terminal_result(connection, job_id, run_id, result)
            return snapshot(self._require_job(connection, job_id))

    @staticmethod
    def _lock_commit_fence(connection, job_id, run_id, fence) -> None:
        if fence is None or fence.stage_run_id != run_id:
            raise CommitFenceRejected("commit fence does not match orchestration run")
        locked = connection.execute(
            "SELECT stage_run_id FROM quality_queue WHERE stage_run_id=%s "
            "AND job_id=%s FOR UPDATE",
            (fence.stage_run_id, job_id),
        ).fetchone()
        if locked is None:
            raise CommitFenceRejected(f"quality commit fence rejected: {run_id}")
        valid = connection.execute(
            "SELECT stage_run_id FROM quality_queue WHERE stage_run_id=%s "
            "AND queue_class = 'QUALITY' AND state = 'RUNNING' "
            "AND lease_owner=%s AND lease_token=%s AND deadline = %s "
            "AND deadline > clock_timestamp() AND lease_expires_at IS NOT NULL "
            "AND lease_expires_at > clock_timestamp()",
            (
                fence.stage_run_id,
                fence.lease_owner,
                fence.lease_token,
                fence.deadline,
            ),
        ).fetchone()
        if valid is None:
            raise CommitFenceRejected(f"quality commit fence rejected: {run_id}")

    @staticmethod
    def _require_version(job, job_id, expected_version) -> None:
        actual = int(job["version"])
        if actual != expected_version:
            raise StaleWrite(job_id, expected_version, actual)

    @staticmethod
    def _require_unfinished_run(run, run_id) -> None:
        if run["result_payload"] is not None:
            raise DuplicateRunConflict(f"run {run_id} already has a result")

    @staticmethod
    def _store_evidence(connection, evidence_hash, payload) -> None:
        row = connection.execute(
            "SELECT payload FROM quality_evidence WHERE evidence_hash=%s",
            (evidence_hash,),
        ).fetchone()
        if row is not None and bytes(row["payload"]) != payload:
            raise DuplicateRunConflict("evidence hash has different payload")
        if row is None:
            connection.execute(
                "INSERT INTO quality_evidence (evidence_hash, payload) VALUES (%s,%s)",
                (evidence_hash, payload),
            )

    @staticmethod
    def _save_terminal_result(connection, job_id, run_id, result) -> None:
        connection.execute(
            "UPDATE quality_runs SET result_payload=%s "
            "WHERE job_id=%s AND run_id=%s AND result_payload IS NULL",
            (result_parameter(result), job_id, run_id),
        )

    @staticmethod
    def _record_rollback(
        connection,
        job_id,
        run_id,
        rollback_to_revision_id,
        failed_revision_id,
        evidence,
        version,
    ) -> None:
        connection.execute(
            "INSERT INTO quality_rollbacks (job_id, run_id, rollback_to_revision_id, "
            "failed_revision_id, reason_code, evidence_hash, job_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                job_id,
                run_id,
                rollback_to_revision_id,
                failed_revision_id,
                evidence.reason_code,
                evidence.evidence_hash,
                version,
            ),
        )
