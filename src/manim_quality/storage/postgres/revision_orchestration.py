"""PostgreSQL orchestration runs, transitions, and certification."""

from __future__ import annotations

from manim_quality.contracts import QualityResult, QualityState, require_transition
from manim_quality.revisions.store import (
    DuplicateRunConflict,
    RollbackRecord,
    TransitionRecord,
    require_evidence_hash,
    require_expected_version,
)
from manim_quality.storage.validation import require_text

from .revision_codec import (
    result_from_payload,
    result_matches,
    result_parameter,
    session,
    snapshot,
)
from .revision_orchestration_support import (
    PostgresRevisionOrchestrationSupportMixin,
)


class PostgresRevisionOrchestrationMixin(PostgresRevisionOrchestrationSupportMixin):
    def begin_run(self, job_id: str, run_id: str, request_hash: str) -> None:
        require_text(job_id, "job_id")
        require_text(run_id, "run_id")
        require_evidence_hash(request_hash)
        with session(self._connection_factory, transaction=True) as connection:
            self._require_job(connection, job_id)
            row = self._run_row(connection, job_id, run_id)
            if row is not None:
                self._require_run_hash(row, run_id, request_hash)
                return
            connection.execute(
                "INSERT INTO quality_runs (job_id, run_id, request_hash) "
                "VALUES (%s,%s,%s)",
                (job_id, run_id, request_hash),
            )

    def get_run_result(self, job_id, run_id, request_hash) -> QualityResult | None:
        with session(self._connection_factory) as connection:
            row = self._run_row(connection, job_id, run_id)
            if row is None:
                return None
            self._require_run_hash(row, run_id, request_hash)
            payload = row["result_payload"]
            return None if payload is None else result_from_payload(payload)

    def save_run_result(self, job_id, run_id, request_hash, result) -> None:
        if not isinstance(result, QualityResult):
            raise TypeError("result must be a QualityResult")
        with session(self._connection_factory, transaction=True) as connection:
            row = self._require_run(connection, job_id, run_id, request_hash)
            if row["result_payload"] is not None:
                if not result_matches(row["result_payload"], result):
                    raise DuplicateRunConflict(f"run {run_id} has a different result")
                return
            cursor = connection.execute(
                "UPDATE quality_runs SET result_payload=%s "
                "WHERE job_id=%s AND run_id=%s AND result_payload IS NULL",
                (result_parameter(result), job_id, run_id),
            )
            if cursor.rowcount == 0:
                current = self._require_run(connection, job_id, run_id, request_hash)
                if not result_matches(current["result_payload"], result):
                    raise DuplicateRunConflict(f"run {run_id} has a different result")

    def transition_state(self, job_id, source, target, evidence, *, expected_version):
        require_expected_version(expected_version)
        require_transition(source, target)
        with session(self._connection_factory, transaction=True) as connection:
            if self._matching_transition(connection, job_id, source, target, evidence):
                return snapshot(self._require_job(connection, job_id))
            job = self._require_state_version(
                connection, job_id, source, expected_version
            )
            self._update_state(
                connection, job_id, target, expected_version, int(job["version"])
            )
            self._record_transition(
                connection, job_id, source, target, evidence, expected_version + 1
            )
            return snapshot(self._require_job(connection, job_id))

    def certify_checkpoint_state(
        self,
        job_id,
        checkpoint,
        revision_id,
        target,
        evidence,
        *,
        expected_version,
    ):
        require_expected_version(expected_version)
        with session(self._connection_factory, transaction=True) as connection:
            if self._matching_transition(connection, job_id, None, target, evidence):
                return snapshot(self._require_job(connection, job_id))
            job = self._require_job(connection, job_id)
            source = QualityState(job["state"])
            require_transition(source, target)
            self._require_state_version(connection, job_id, source, expected_version)
            self._require_promotable(connection, job_id, checkpoint, revision_id, job)
            self._update_checkpoint_state(
                connection,
                job_id,
                checkpoint,
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
                checkpoint,
                revision_id,
                evidence.evidence_hash,
                version,
            )
            self._record_transition(
                connection, job_id, source, target, evidence, version
            )
            return snapshot(self._require_job(connection, job_id))

    def list_transitions(self, job_id: str) -> tuple[TransitionRecord, ...]:
        with session(self._connection_factory) as connection:
            rows = connection.execute(
                "SELECT * FROM quality_state_transitions WHERE job_id=%s "
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
                    int(row["job_version"]),
                )
                for row in rows
            )

    def list_rollbacks(self, job_id: str) -> tuple[RollbackRecord, ...]:
        with session(self._connection_factory) as connection:
            rows = connection.execute(
                "SELECT * FROM quality_rollbacks WHERE job_id=%s ORDER BY job_version",
                (job_id,),
            ).fetchall()
            return tuple(
                RollbackRecord(
                    row["job_id"],
                    row["run_id"],
                    row["rollback_to_revision_id"],
                    row["failed_revision_id"],
                    row["reason_code"],
                    row["evidence_hash"],
                    int(row["job_version"]),
                )
                for row in rows
            )
