"""Private PostgreSQL orchestration validation and SQL."""

from manim_quality.contracts import QualityState
from manim_quality.revisions.store import (
    CheckpointConflict,
    DuplicateRunConflict,
    StaleWrite,
    TransitionEvidence,
    TransitionReplayAdvanced,
)
from manim_quality.storage.validation import evidence_field


class PostgresRevisionOrchestrationSupportMixin:
    def _matching_transition(
        self, connection, job_id, source, target, evidence: TransitionEvidence
    ) -> bool:
        row = connection.execute(
            "SELECT * FROM quality_state_transitions WHERE job_id=%s AND run_id=%s",
            (job_id, evidence.run_id),
        ).fetchone()
        if row is None:
            return False
        expected = (target.value, evidence.reason_code, evidence.evidence_hash)
        actual = (row["target_state"], row["reason_code"], row["evidence_hash"])
        wrong_source = source is not None and row["source_state"] != source.value
        if expected != actual or wrong_source:
            raise DuplicateRunConflict(f"transition run {evidence.run_id} conflicts")
        job = self._require_job(connection, job_id)
        if (
            int(job["version"]) != int(row["job_version"])
            or job["state"] != row["target_state"]
        ):
            raise TransitionReplayAdvanced(
                f"transition {evidence.run_id} was followed by newer state"
            )
        return True

    def _require_state_version(self, connection, job_id, state, expected):
        job = self._require_job(connection, job_id)
        if int(job["version"]) != expected:
            raise StaleWrite(job_id, expected, int(job["version"]))
        if QualityState(job["state"]) is not state:
            raise CheckpointConflict(f"job is {job['state']}, expected {state.value}")
        return job

    @staticmethod
    def _update_state(connection, job_id, target, expected, actual) -> None:
        cursor = connection.execute(
            "UPDATE quality_jobs SET state=%s, version=version+1 "
            "WHERE job_id=%s AND version=%s",
            (target.value, job_id, expected),
        )
        if cursor.rowcount != 1:
            raise StaleWrite(job_id, expected, actual)

    def _require_promotable(self, connection, job_id, checkpoint, revision_id, job):
        self._require_owned_revision(connection, job_id, revision_id)
        self._require_checkpoint_path(
            connection, job_id, revision_id, checkpoint, job, job[checkpoint.value]
        )

    @staticmethod
    def _update_checkpoint_state(
        connection,
        job_id,
        checkpoint,
        revision_id,
        target,
        evidence_hash,
        expected,
        actual,
    ) -> None:
        field = evidence_field(checkpoint)
        cursor = connection.execute(
            f"UPDATE quality_jobs SET {checkpoint.value}=%s, {field}=%s, "
            "state=%s, version=version+1 WHERE job_id=%s AND version=%s",
            (revision_id, evidence_hash, target.value, job_id, expected),
        )
        if cursor.rowcount != 1:
            raise StaleWrite(job_id, expected, actual)

    @staticmethod
    def _record_transition(connection, job_id, source, target, evidence, version):
        connection.execute(
            "INSERT INTO quality_state_transitions (job_id, run_id, reason_code, "
            "evidence_hash, source_state, target_state, job_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                job_id,
                evidence.run_id,
                evidence.reason_code,
                evidence.evidence_hash,
                source.value,
                target.value,
                version,
            ),
        )

    @staticmethod
    def _run_row(connection, job_id, run_id):
        return connection.execute(
            "SELECT * FROM quality_runs WHERE job_id=%s AND run_id=%s",
            (job_id, run_id),
        ).fetchone()

    def _require_run(self, connection, job_id, run_id, request_hash):
        row = self._run_row(connection, job_id, run_id)
        if row is None:
            raise DuplicateRunConflict(f"run {run_id} is missing or conflicts")
        self._require_run_hash(row, run_id, request_hash)
        return row

    @staticmethod
    def _require_run_hash(row, run_id, request_hash) -> None:
        if row["request_hash"] != request_hash:
            raise DuplicateRunConflict(f"run {run_id} has a different payload")
