"""Standard-library SQLite adapter for the revision repository port."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from manim_quality.contracts import QualityState, Revision, RevisionStage
from manim_quality.revisions.store import (
    Checkpoint,
    CheckpointConflict,
    CheckpointOrderError,
    JobConflict,
    JobNotFound,
    ParentRevisionError,
    QualityJobSnapshot,
    RevisionConflict,
    RevisionJobMismatch,
    RevisionNotFound,
    StaleWrite,
    require_evidence_hash,
    require_expected_version,
)

from ._checkpoint_records import record_checkpoint
from ._checkpoint_rules import checkpoint_prerequisite, evidence_field
from ._revision_records import (
    revision_from_row,
    revision_values,
    row_matches,
    snapshot_from_row,
)
from ._sqlite import open_sqlite, transaction
from .orchestration import SQLiteOrchestrationMixin
from .validation import require_revision, require_text


class SQLiteRevisionRepository(SQLiteOrchestrationMixin):
    """Local/test repository with immutable revisions and versioned CAS writes."""

    def __init__(self, database: str | Path) -> None:
        self._connection = open_sqlite(database)

    def close(self) -> None:
        self._connection.close()

    def create_job(self, job_id: str, baseline: Revision) -> QualityJobSnapshot:
        require_text(job_id, "job_id")
        require_revision(baseline)
        if baseline.parent_revision_id is not None:
            raise ParentRevisionError("job baseline must be the single BASELINE root")
        if baseline.stage is not RevisionStage.BASELINE:
            raise ParentRevisionError("job baseline must be the single BASELINE root")
        if baseline.render_manifest_hash is None:
            raise CheckpointOrderError(
                "job baseline requires a successful render manifest hash"
            )
        with transaction(self._connection):
            current = self._find_job(job_id)
            if current is not None:
                return self._idempotent_job(current, baseline)
            existing = self._find_revision(baseline.revision_id)
            if existing is not None:
                raise RevisionConflict(
                    f"revision {baseline.revision_id} already belongs to another job"
                )
            self._connection.execute(
                """
                INSERT INTO quality_jobs (
                    job_id, version, state, render_baseline_revision_id,
                    render_baseline_evidence_hash
                ) VALUES (?, 0, ?, ?, ?)
                """,
                (
                    job_id,
                    QualityState.BASELINE_READY.value,
                    baseline.revision_id,
                    baseline.render_manifest_hash,
                ),
            )
            self._insert_revision(job_id, baseline)
            record_checkpoint(
                self._connection,
                job_id,
                Checkpoint.RENDER_BASELINE,
                baseline.revision_id,
                baseline.render_manifest_hash,
                version=0,
            )
            return snapshot_from_row(self._require_job(job_id))

    def append_revision(
        self,
        job_id: str,
        revision: Revision,
        *,
        expected_version: int,
    ) -> QualityJobSnapshot:
        require_text(job_id, "job_id")
        require_revision(revision)
        require_expected_version(expected_version)
        with transaction(self._connection):
            existing = self._find_revision(revision.revision_id)
            if existing is not None:
                if row_matches(existing, job_id, revision):
                    return snapshot_from_row(self._require_job(job_id))
                raise RevisionConflict(
                    f"revision {revision.revision_id} has a different payload"
                )
            job = self._require_job(job_id)
            self._require_parent(job_id, revision)
            self._insert_revision(job_id, revision)
            self._cas_version(job_id, expected_version, int(job["version"]))
            return snapshot_from_row(self._require_job(job_id))

    def promote_checkpoint(
        self,
        job_id: str,
        checkpoint: Checkpoint,
        revision_id: str,
        *,
        evidence_hash: str,
        expected_version: int,
    ) -> QualityJobSnapshot:
        require_text(job_id, "job_id")
        require_text(revision_id, "revision_id")
        if not isinstance(checkpoint, Checkpoint):
            raise TypeError("checkpoint must be a Checkpoint")
        require_evidence_hash(evidence_hash)
        require_expected_version(expected_version)
        if checkpoint is Checkpoint.RENDER_BASELINE:
            raise CheckpointConflict("render baseline checkpoint is immutable")
        with transaction(self._connection):
            job = self._require_job(job_id)
            revision = self._find_revision(revision_id)
            if revision is None:
                raise RevisionNotFound(f"revision not found: {revision_id}")
            if revision["job_id"] != job_id:
                raise RevisionJobMismatch(
                    f"revision {revision_id} does not belong to job {job_id}"
                )
            checkpoint_evidence_field = evidence_field(checkpoint)
            current_revision_id = job[checkpoint.value]
            current_evidence_hash = job[checkpoint_evidence_field]
            if current_revision_id == revision_id:
                if current_evidence_hash != evidence_hash:
                    raise CheckpointConflict(
                        f"{checkpoint.name} already has different evidence"
                    )
                return snapshot_from_row(job)
            self._require_checkpoint_path(
                job_id, revision_id, checkpoint, job, current_revision_id
            )
            cursor = self._connection.execute(
                f"""
                UPDATE quality_jobs
                SET {checkpoint.value} = ?, {checkpoint_evidence_field} = ?,
                    version = version + 1
                WHERE job_id = ? AND version = ?
                """,
                (revision_id, evidence_hash, job_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise StaleWrite(job_id, expected_version, int(job["version"]))
            record_checkpoint(
                self._connection,
                job_id,
                checkpoint,
                revision_id,
                evidence_hash,
                version=expected_version + 1,
            )
            return snapshot_from_row(self._require_job(job_id))

    def get_job(self, job_id: str) -> QualityJobSnapshot:
        require_text(job_id, "job_id")
        return snapshot_from_row(self._require_job(job_id))

    def get_revision(self, revision_id: str) -> Revision:
        require_text(revision_id, "revision_id")
        row = self._connection.execute(
            "SELECT payload FROM quality_revisions WHERE revision_id = ?",
            (revision_id,),
        ).fetchone()
        if row is None:
            raise RevisionNotFound(f"revision not found: {revision_id}")
        return revision_from_row(row)

    def _idempotent_job(
        self, current: sqlite3.Row, baseline: Revision
    ) -> QualityJobSnapshot:
        if current["render_baseline_revision_id"] != baseline.revision_id:
            raise JobConflict(f"job {current['job_id']} has a different baseline")
        existing = self._find_revision(baseline.revision_id)
        if existing is None or not row_matches(existing, current["job_id"], baseline):
            raise RevisionConflict(
                f"revision {baseline.revision_id} has a different payload"
            )
        return snapshot_from_row(current)

    def _require_parent(self, job_id: str, revision: Revision) -> None:
        parent_id = revision.parent_revision_id
        if parent_id is None or revision.stage is RevisionStage.BASELINE:
            raise ParentRevisionError("only create_job may create the BASELINE root")
        parent = self._find_revision(parent_id)
        if parent is None:
            raise ParentRevisionError(f"parent revision not found: {parent_id}")
        if parent["job_id"] != job_id:
            raise ParentRevisionError(f"parent {parent_id} belongs to another job")

    def _cas_version(self, job_id: str, expected: int, actual: int) -> None:
        cursor = self._connection.execute(
            """
            UPDATE quality_jobs SET version = version + 1
            WHERE job_id = ? AND version = ?
            """,
            (job_id, expected),
        )
        if cursor.rowcount != 1:
            raise StaleWrite(job_id, expected, actual)

    def _insert_revision(self, job_id: str, revision: Revision) -> None:
        self._connection.execute(
            """
            INSERT INTO quality_revisions (
                revision_id, job_id, parent_revision_id, stage, payload,
                code_hash, semantic_fingerprint, render_manifest_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            revision_values(job_id, revision),
        )

    def _is_descendant(self, job_id: str, revision_id: str, ancestor_id: str) -> bool:
        current_id: str | None = revision_id
        visited: set[str] = set()
        while current_id is not None and current_id not in visited:
            if current_id == ancestor_id:
                return True
            visited.add(current_id)
            row = self._find_revision(current_id)
            if row is None or row["job_id"] != job_id:
                return False
            current_id = row["parent_revision_id"]
        return False

    def _require_checkpoint_path(
        self,
        job_id: str,
        revision_id: str,
        checkpoint: Checkpoint,
        job: sqlite3.Row,
        current_revision_id: str | None,
    ) -> None:
        prerequisite = checkpoint_prerequisite(checkpoint)
        prerequisite_revision_id = job[prerequisite.value]
        if prerequisite_revision_id is None:
            raise CheckpointOrderError(
                f"{checkpoint.name} requires {prerequisite.name}"
            )
        if not self._is_descendant(job_id, revision_id, prerequisite_revision_id):
            raise CheckpointOrderError(
                f"revision {revision_id} does not descend from {prerequisite.name}"
            )
        if current_revision_id is not None and not self._is_descendant(
            job_id, revision_id, current_revision_id
        ):
            raise CheckpointConflict(
                f"{checkpoint.name} cannot move to a non-descendant revision"
            )

    def _find_revision(self, revision_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT job_id, parent_revision_id, payload
            FROM quality_revisions WHERE revision_id = ?
            """,
            (revision_id,),
        ).fetchone()

    def _find_job(self, job_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM quality_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()

    def _require_job(self, job_id: str) -> sqlite3.Row:
        row = self._find_job(job_id)
        if row is None:
            raise JobNotFound(f"job not found: {job_id}")
        return row
