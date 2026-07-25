"""PostgreSQL immutable revisions and checkpoint CAS operations."""

from __future__ import annotations

from manim_quality.contracts import QualityState, Revision
from manim_quality.revisions.store import (
    Checkpoint,
    CheckpointConflict,
    RevisionConflict,
    RevisionNotFound,
    StaleWrite,
    require_evidence_hash,
    require_expected_version,
)
from manim_quality.storage.validation import (
    evidence_field,
    require_revision,
    require_text,
)

from .revision_codec import (
    revision_from_row,
    revision_matches,
    session,
    snapshot,
)
from .revision_record_support import PostgresRevisionRecordSupportMixin


class PostgresRevisionRecordsMixin(PostgresRevisionRecordSupportMixin):
    def create_job(self, job_id: str, baseline: Revision):
        require_text(job_id, "job_id")
        require_revision(baseline)
        self._validate_baseline(baseline)
        with session(self._connection_factory, transaction=True) as connection:
            current = self._find_job(connection, job_id)
            if current is not None:
                return self._idempotent_job(connection, current, baseline)
            existing = self._find_revision(connection, baseline.revision_id)
            if existing is not None:
                raise RevisionConflict(
                    f"revision {baseline.revision_id} already belongs to another job"
                )
            connection.execute(
                "INSERT INTO quality_jobs (job_id, version, state, "
                "render_baseline_revision_id, render_baseline_evidence_hash) "
                "VALUES (%s, 0, %s, %s, %s)",
                (
                    job_id,
                    QualityState.BASELINE_READY.value,
                    baseline.revision_id,
                    baseline.render_manifest_hash,
                ),
            )
            self._insert_revision(connection, job_id, baseline)
            self._record_checkpoint(
                connection,
                job_id,
                Checkpoint.RENDER_BASELINE,
                baseline.revision_id,
                baseline.render_manifest_hash,
                0,
            )
            return snapshot(self._require_job(connection, job_id))

    def append_revision(self, job_id, revision, *, expected_version):
        require_text(job_id, "job_id")
        require_revision(revision)
        require_expected_version(expected_version)
        with session(self._connection_factory, transaction=True) as connection:
            existing = self._find_revision(connection, revision.revision_id)
            if existing is not None:
                if revision_matches(existing, job_id, revision):
                    return snapshot(self._require_job(connection, job_id))
                raise RevisionConflict(
                    f"revision {revision.revision_id} has a different payload"
                )
            job = self._require_job(connection, job_id)
            self._require_parent(connection, job_id, revision)
            self._insert_revision(connection, job_id, revision)
            self._cas_version(connection, job_id, expected_version, int(job["version"]))
            return snapshot(self._require_job(connection, job_id))

    def promote_checkpoint(
        self, job_id, checkpoint, revision_id, *, evidence_hash, expected_version
    ):
        require_text(job_id, "job_id")
        require_text(revision_id, "revision_id")
        if not isinstance(checkpoint, Checkpoint):
            raise TypeError("checkpoint must be a Checkpoint")
        require_evidence_hash(evidence_hash)
        require_expected_version(expected_version)
        if checkpoint is Checkpoint.RENDER_BASELINE:
            raise CheckpointConflict("render baseline checkpoint is immutable")
        with session(self._connection_factory, transaction=True) as connection:
            job = self._require_job(connection, job_id)
            revision = self._require_owned_revision(connection, job_id, revision_id)
            del revision
            field = evidence_field(checkpoint)
            if job[checkpoint.value] == revision_id:
                if job[field] != evidence_hash:
                    raise CheckpointConflict(
                        f"{checkpoint.name} already has different evidence"
                    )
                return snapshot(job)
            self._require_checkpoint_path(
                connection, job_id, revision_id, checkpoint, job, job[checkpoint.value]
            )
            cursor = connection.execute(
                f"UPDATE quality_jobs SET {checkpoint.value}=%s, {field}=%s, "
                "version=version+1 WHERE job_id=%s AND version=%s",
                (revision_id, evidence_hash, job_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise StaleWrite(job_id, expected_version, int(job["version"]))
            self._record_checkpoint(
                connection,
                job_id,
                checkpoint,
                revision_id,
                evidence_hash,
                expected_version + 1,
            )
            return snapshot(self._require_job(connection, job_id))

    def get_job(self, job_id: str):
        require_text(job_id, "job_id")
        with session(self._connection_factory) as connection:
            return snapshot(self._require_job(connection, job_id))

    def get_revision(self, revision_id: str) -> Revision:
        require_text(revision_id, "revision_id")
        with session(self._connection_factory) as connection:
            row = connection.execute(
                "SELECT payload FROM quality_revisions WHERE revision_id=%s",
                (revision_id,),
            ).fetchone()
            if row is None:
                raise RevisionNotFound(f"revision not found: {revision_id}")
            return revision_from_row(row)
