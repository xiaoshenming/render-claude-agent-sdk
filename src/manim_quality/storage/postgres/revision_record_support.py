"""Private PostgreSQL revision record rules and SQL."""

from manim_quality.contracts import Revision, RevisionStage
from manim_quality.revisions.store import (
    CheckpointConflict,
    CheckpointOrderError,
    JobConflict,
    JobNotFound,
    ParentRevisionError,
    RevisionConflict,
    RevisionJobMismatch,
    RevisionNotFound,
    StaleWrite,
)
from manim_quality.storage.validation import checkpoint_prerequisite

from .revision_codec import revision_matches, revision_parameter, snapshot


class PostgresRevisionRecordSupportMixin:
    @staticmethod
    def _validate_baseline(baseline: Revision) -> None:
        if (
            baseline.parent_revision_id is not None
            or baseline.stage is not RevisionStage.BASELINE
        ):
            raise ParentRevisionError("job baseline must be the single BASELINE root")
        if baseline.render_manifest_hash is None:
            raise CheckpointOrderError(
                "job baseline requires a successful render manifest hash"
            )

    def _idempotent_job(self, connection, current, baseline):
        if current["render_baseline_revision_id"] != baseline.revision_id:
            raise JobConflict(f"job {current['job_id']} has a different baseline")
        existing = self._find_revision(connection, baseline.revision_id)
        if existing is None or not revision_matches(
            existing, current["job_id"], baseline
        ):
            raise RevisionConflict(
                f"revision {baseline.revision_id} has a different payload"
            )
        return snapshot(current)

    def _require_parent(self, connection, job_id: str, revision: Revision) -> None:
        parent_id = revision.parent_revision_id
        if parent_id is None or revision.stage is RevisionStage.BASELINE:
            raise ParentRevisionError("only create_job may create the BASELINE root")
        parent = self._find_revision(connection, parent_id)
        if parent is None:
            raise ParentRevisionError(f"parent revision not found: {parent_id}")
        if parent["job_id"] != job_id:
            raise ParentRevisionError(f"parent {parent_id} belongs to another job")

    @staticmethod
    def _insert_revision(connection, job_id: str, revision: Revision) -> None:
        connection.execute(
            "INSERT INTO quality_revisions (revision_id, job_id, parent_revision_id, "
            "stage, payload, code_hash, semantic_fingerprint, render_manifest_hash) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                revision.revision_id,
                job_id,
                revision.parent_revision_id,
                revision.stage.value,
                revision_parameter(revision),
                revision.code_hash,
                revision.semantic_fingerprint,
                revision.render_manifest_hash,
            ),
        )

    @staticmethod
    def _cas_version(connection, job_id: str, expected: int, actual: int) -> None:
        cursor = connection.execute(
            "UPDATE quality_jobs SET version=version+1 "
            "WHERE job_id=%s AND version = %s",
            (job_id, expected),
        )
        if cursor.rowcount != 1:
            raise StaleWrite(job_id, expected, actual)

    def _require_checkpoint_path(
        self, connection, job_id, revision_id, checkpoint, job, current_revision_id
    ) -> None:
        prerequisite = checkpoint_prerequisite(checkpoint)
        prerequisite_id = job[prerequisite.value]
        if prerequisite_id is None:
            raise CheckpointOrderError(
                f"{checkpoint.name} requires {prerequisite.name}"
            )
        if not self._is_descendant(connection, job_id, revision_id, prerequisite_id):
            raise CheckpointOrderError(
                f"revision {revision_id} does not descend from {prerequisite.name}"
            )
        if current_revision_id is not None and not self._is_descendant(
            connection, job_id, revision_id, current_revision_id
        ):
            raise CheckpointConflict(
                f"{checkpoint.name} cannot move to a non-descendant revision"
            )

    def _is_descendant(self, connection, job_id, revision_id, ancestor_id) -> bool:
        current_id, visited = revision_id, set()
        while current_id is not None and current_id not in visited:
            if current_id == ancestor_id:
                return True
            visited.add(current_id)
            row = self._find_revision(connection, current_id)
            if row is None or row["job_id"] != job_id:
                return False
            current_id = row["parent_revision_id"]
        return False

    def _require_owned_revision(self, connection, job_id, revision_id):
        revision = self._find_revision(connection, revision_id)
        if revision is None:
            raise RevisionNotFound(f"revision not found: {revision_id}")
        if revision["job_id"] != job_id:
            raise RevisionJobMismatch(f"revision {revision_id} belongs to another job")
        return revision

    @staticmethod
    def _find_revision(connection, revision_id):
        return connection.execute(
            "SELECT job_id, parent_revision_id, payload FROM quality_revisions "
            "WHERE revision_id=%s",
            (revision_id,),
        ).fetchone()

    @staticmethod
    def _find_job(connection, job_id):
        return connection.execute(
            "SELECT * FROM quality_jobs WHERE job_id=%s", (job_id,)
        ).fetchone()

    def _require_job(self, connection, job_id):
        row = self._find_job(connection, job_id)
        if row is None:
            raise JobNotFound(f"job not found: {job_id}")
        return row

    @staticmethod
    def _record_checkpoint(
        connection, job_id, checkpoint, revision_id, evidence_hash, version
    ) -> None:
        connection.execute(
            "INSERT INTO quality_checkpoint_history "
            "(job_id, checkpoint, revision_id, evidence_hash, job_version) "
            "VALUES (%s,%s,%s,%s,%s)",
            (job_id, checkpoint.name, revision_id, evidence_hash, version),
        )
