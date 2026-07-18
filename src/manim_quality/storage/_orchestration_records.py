"""Low-level immutable transition and evidence records for SQLite."""

import sqlite3

from manim_quality.contracts import QualityState
from manim_quality.revisions.store import (
    Checkpoint,
    CheckpointConflict,
    DuplicateRunConflict,
    RevisionJobMismatch,
    RevisionNotFound,
    StaleWrite,
    TransitionEvidence,
    TransitionReplayAdvanced,
)

from ._checkpoint_rules import evidence_field
from ._run_records import SQLiteRunRecordsMixin


class SQLiteOrchestrationRecordsMixin(SQLiteRunRecordsMixin):
    _connection: sqlite3.Connection

    def _matching_transition(
        self,
        job_id: str,
        source: QualityState | None,
        target: QualityState,
        evidence: TransitionEvidence,
    ) -> bool:
        row = self._connection.execute(
            "SELECT * FROM quality_state_transitions WHERE job_id = ? AND run_id = ?",
            (job_id, evidence.run_id),
        ).fetchone()
        if row is None:
            return False
        expected = (target.value, evidence.reason_code, evidence.evidence_hash)
        actual = (row["target_state"], row["reason_code"], row["evidence_hash"])
        wrong_source = source is not None and row["source_state"] != source.value
        if expected != actual or wrong_source:
            raise DuplicateRunConflict(f"transition run {evidence.run_id} conflicts")
        job = self._require_job(job_id)
        if (
            int(job["version"]) != int(row["job_version"])
            or job["state"] != row["target_state"]
        ):
            raise TransitionReplayAdvanced(
                f"transition {evidence.run_id} was followed by newer state"
            )
        return True

    def _require_state_version(
        self, job_id: str, state: QualityState, expected: int
    ) -> sqlite3.Row:
        job = self._require_job(job_id)
        if int(job["version"]) != expected:
            raise StaleWrite(job_id, expected, int(job["version"]))
        if QualityState(job["state"]) is not state:
            raise CheckpointConflict(f"job is {job['state']}, expected {state.value}")
        return job

    def _update_state(
        self, job_id: str, target: QualityState, expected: int, actual: int
    ) -> None:
        cursor = self._connection.execute(
            "UPDATE quality_jobs SET state = ?, version = version + 1 "
            "WHERE job_id = ? AND version = ?",
            (target.value, job_id, expected),
        )
        if cursor.rowcount != 1:
            raise StaleWrite(job_id, expected, actual)

    def _require_promotable(
        self, job_id: str, checkpoint: Checkpoint, revision_id: str, job: sqlite3.Row
    ) -> None:
        revision = self._find_revision(revision_id)
        if revision is None:
            raise RevisionNotFound(f"revision not found: {revision_id}")
        if revision["job_id"] != job_id:
            raise RevisionJobMismatch(f"revision {revision_id} belongs to another job")
        self._require_checkpoint_path(
            job_id, revision_id, checkpoint, job, job[checkpoint.value]
        )

    def _require_owned_revision(self, job_id: str, revision_id: str) -> None:
        revision = self._find_revision(revision_id)
        if revision is None:
            raise RevisionNotFound(f"revision not found: {revision_id}")
        if revision["job_id"] != job_id:
            raise RevisionJobMismatch(f"revision {revision_id} belongs to another job")

    def _update_checkpoint_state(
        self,
        job_id: str,
        checkpoint: Checkpoint,
        revision_id: str,
        target: QualityState,
        evidence_hash: str,
        expected: int,
        actual: int,
    ) -> None:
        field = evidence_field(checkpoint)
        cursor = self._connection.execute(
            f"UPDATE quality_jobs SET {checkpoint.value} = ?, {field} = ?, "
            "state = ?, version = version + 1 WHERE job_id = ? AND version = ?",
            (revision_id, evidence_hash, target.value, job_id, expected),
        )
        if cursor.rowcount != 1:
            raise StaleWrite(job_id, expected, actual)

    def _record_transition(
        self,
        job_id: str,
        source: QualityState,
        target: QualityState,
        evidence: TransitionEvidence,
        version: int,
    ) -> None:
        self._connection.execute(
            "INSERT INTO quality_state_transitions "
            "(job_id, run_id, reason_code, evidence_hash, source_state, "
            "target_state, job_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
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

    def _store_evidence(self, evidence_hash: str, payload: bytes) -> None:
        row = self._connection.execute(
            "SELECT payload FROM quality_evidence WHERE evidence_hash = ?",
            (evidence_hash,),
        ).fetchone()
        if row is not None and bytes(row["payload"]) != payload:
            raise DuplicateRunConflict("evidence hash has different payload")
        if row is None:
            self._connection.execute(
                "INSERT INTO quality_evidence (evidence_hash, payload) VALUES (?, ?)",
                (evidence_hash, payload),
            )
