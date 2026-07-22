from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from psycopg import OperationalError

from manim_quality.contracts import DeliveryDecision, QualityResult, QualityState
from manim_quality.revisions.fence import CommitFence
from manim_quality.revisions.store import (
    CommitFenceRejected,
    DuplicateRunConflict,
    RepositoryTransactionError,
    RevisionRepository,
    StaleWrite,
    TransitionEvidence,
)
from manim_quality.storage.factory import create_storage_factories
from manim_quality.storage.postgres import PostgresRevisionRepository
from tests.e2e.test_quality_happy_path import baseline, digest
from tests.unit.storage.postgres_fakes import Connection, Cursor



from test_postgres_revision_repository_support import *
def test_terminal_accept_locks_and_validates_fence_before_any_write() -> None:
    connection = Connection(terminal_responder(QualityState.ACCEPTED))

    snapshot = finalize_delivery(PostgresRevisionRepository(lambda: connection))

    assert snapshot.state is QualityState.ACCEPTED
    lock_sql, lock_parameters = connection.executed[0]
    validate_sql, validate_parameters = connection.executed[1]
    assert "FROM quality_queue" in lock_sql and "FOR UPDATE" in lock_sql
    assert "stage_run_id=%s" in lock_sql and "job_id=%s" in lock_sql
    assert "clock_timestamp" not in lock_sql
    assert "queue_class = 'QUALITY'" in validate_sql
    assert "state = 'RUNNING'" in validate_sql
    assert "deadline = %s" in validate_sql
    assert "deadline > clock_timestamp()" in validate_sql
    assert "lease_expires_at > clock_timestamp()" in validate_sql
    assert lock_parameters == ("run-1", "job-1")
    assert validate_parameters == (
        "run-1",
        "worker-a",
        "token-a",
        fence().deadline,
    )
    first_write = next(
        i for i, (item, _) in enumerate(connection.executed) if _is_write(item)
    )
    assert first_write > 1
    assert connection.events == ["BEGIN", "COMMIT"]


def test_stale_terminal_fence_rolls_back_without_mutation() -> None:
    connection = Connection(lambda sql, parameters: Cursor())
    repository = PostgresRevisionRepository(lambda: connection)

    with pytest.raises(CommitFenceRejected):
        finalize_delivery(repository)

    assert len(connection.executed) == 1
    assert not any(_is_write(sql) for sql, _ in connection.executed)
    assert connection.events == ["BEGIN", "ROLLBACK"]


def test_postgres_failure_rolls_back_and_maps_transaction_error() -> None:
    def respond(sql, parameters):
        if "FROM quality_queue" in sql:
            return Cursor(({"stage_run_id": "run-1"},))
        return OperationalError("database unavailable")

    connection = Connection(respond)

    with pytest.raises(RepositoryTransactionError, match="database unavailable"):
        finalize_delivery(PostgresRevisionRepository(lambda: connection))

    assert connection.events == ["BEGIN", "ROLLBACK"]


def test_connection_failure_maps_transaction_error() -> None:
    def fail_connection():
        raise OperationalError("connection unavailable")

    repository = PostgresRevisionRepository(fail_connection)

    with pytest.raises(RepositoryTransactionError, match="connection unavailable"):
        repository.get_job("job-1")


def test_accept_mutations_are_atomic_and_ordered_after_fence() -> None:
    connection = Connection(terminal_responder(QualityState.ACCEPTED))
    finalize_delivery(PostgresRevisionRepository(lambda: connection))

    statements = [sql for sql, _ in connection.executed]
    assert _index(statements, "INSERT INTO quality_evidence") > 0
    assert _index(statements, "UPDATE quality_jobs") > 0
    assert _index(statements, "INSERT INTO quality_checkpoint_history") > 0
    assert _index(statements, "INSERT INTO quality_state_transitions") > 0
    assert _index(statements, "UPDATE quality_runs") > 0
    assert connection.events == ["BEGIN", "COMMIT"]


def test_hold_mutations_include_rollback_and_result_in_same_transaction() -> None:
    connection = Connection(terminal_responder(QualityState.HOLD))
    repository = PostgresRevisionRepository(lambda: connection)
    evidence = TransitionEvidence("run-1", "held", digest("hold evidence"))

    snapshot = repository.finalize_hold(
        "job-1",
        "baseline",
        None,
        evidence,
        b"hold evidence",
        result(DeliveryDecision.HOLD),
        run_id="run-1",
        request_hash=digest("request"),
        expected_version=3,
        commit_fence=fence(),
    )

    statements = [sql for sql, _ in connection.executed]
    assert snapshot.state is QualityState.HOLD
    assert _index(statements, "INSERT INTO quality_rollbacks") > 0
    assert _index(statements, "UPDATE quality_runs") > 0
    assert connection.events == ["BEGIN", "COMMIT"]
