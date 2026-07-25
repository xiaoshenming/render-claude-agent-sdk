"""PostgreSQL revision encoding and transaction boundaries."""

from __future__ import annotations

import json
from contextlib import contextmanager

from psycopg import Error
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from manim_quality.contracts import QualityResult, QualityState, Revision
from manim_quality.revisions.store import (
    CheckpointConflict,
    DuplicateRunConflict,
    JobConflict,
    QualityJobSnapshot,
    RepositoryError,
    RepositoryTransactionError,
    RevisionConflict,
)


@contextmanager
def session(connection_factory, *, transaction: bool = False):
    connection = None
    try:
        try:
            connection = connection_factory()
            if transaction:
                with connection.transaction():
                    yield connection
            else:
                yield connection
        except RepositoryError:
            raise
        except UniqueViolation as error:
            raise _unique_conflict(error) from error
        except Error as error:
            raise RepositoryTransactionError(str(error)) from error
    finally:
        if connection is not None:
            connection.close()


def revision_payload(revision: Revision) -> dict[str, object]:
    return revision.to_dict()


def revision_parameter(revision: Revision) -> Jsonb:
    return Jsonb(revision_payload(revision))


def revision_from_row(row) -> Revision:
    return Revision.from_dict(_json_object(row["payload"]))


def revision_matches(row, job_id: str, revision: Revision) -> bool:
    return row["job_id"] == job_id and _json_object(row["payload"]) == revision_payload(
        revision
    )


def result_parameter(result: QualityResult) -> Jsonb:
    return Jsonb(result.to_dict())


def result_from_payload(payload) -> QualityResult:
    return QualityResult.from_dict(_json_object(payload))


def result_matches(payload, result: QualityResult) -> bool:
    return _json_object(payload) == result.to_dict()


def snapshot(row) -> QualityJobSnapshot:
    return QualityJobSnapshot(
        job_id=row["job_id"],
        version=int(row["version"]),
        state=QualityState(row["state"]),
        render_baseline_revision_id=row["render_baseline_revision_id"],
        logic_certified_revision_id=row["logic_certified_revision_id"],
        layout_certified_revision_id=row["layout_certified_revision_id"],
        delivery_revision_id=row["delivery_revision_id"],
        render_baseline_evidence_hash=row["render_baseline_evidence_hash"],
        logic_certified_evidence_hash=row["logic_certified_evidence_hash"],
        layout_certified_evidence_hash=row["layout_certified_evidence_hash"],
        delivery_evidence_hash=row["delivery_evidence_hash"],
    )


def _json_object(value) -> dict[str, object]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        value = dict(value)
    return value


def _unique_conflict(error: UniqueViolation) -> RepositoryError:
    constraint = getattr(getattr(error, "diag", None), "constraint_name", "") or ""
    if "quality_jobs" in constraint:
        return JobConflict("job identity conflicts")
    if "quality_revisions" in constraint or "revision_one_root" in constraint:
        return RevisionConflict("revision identity conflicts")
    if "checkpoint" in constraint:
        return CheckpointConflict("checkpoint history conflicts")
    run_constraints = ("quality_runs", "state_transitions", "rollbacks")
    if any(name in constraint for name in run_constraints):
        return DuplicateRunConflict("run identity conflicts")
    return RepositoryTransactionError(str(error))
