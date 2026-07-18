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


def job_row(*, version: int = 0, state: str = "BASELINE_READY"):
    return {
        "job_id": "job-1",
        "version": version,
        "state": state,
        "render_baseline_revision_id": "baseline",
        "logic_certified_revision_id": "baseline",
        "layout_certified_revision_id": "baseline",
        "delivery_revision_id": None,
        "render_baseline_evidence_hash": digest("manifest:baseline"),
        "logic_certified_evidence_hash": digest("logic"),
        "layout_certified_evidence_hash": digest("layout"),
        "delivery_evidence_hash": None,
    }


def fence() -> CommitFence:
    return CommitFence("run-1", "worker-a", "token-a", datetime(2030, 1, 1, tzinfo=UTC))


def result(decision: DeliveryDecision) -> QualityResult:
    accepted = decision in {
        DeliveryDecision.ACCEPT,
        DeliveryDecision.ACCEPT_WITH_WARNING,
    }
    return QualityResult(
        "job-1",
        decision,
        "baseline" if accepted else None,
        "artifact://code" if accepted else None,
        "artifact://render" if accepted else None,
        "artifact://certificate",
        (),
        {},
        {},
    )


def terminal_responder(target: QualityState):
    jobs = [job_row(version=3, state="FINAL_CONSISTENCY_GATE")]
    jobs.append(job_row(version=4, state=target.value))

    def respond(sql, parameters):
        if "FROM quality_queue" in sql:
            return Cursor(({"stage_run_id": "run-1"},))
        if "FROM quality_state_transitions" in sql:
            return Cursor()
        if "FROM quality_jobs" in sql:
            return Cursor((jobs.pop(0),))
        if "FROM quality_revisions" in sql:
            row = {
                "job_id": "job-1",
                "parent_revision_id": None,
                "payload": baseline().to_dict(),
            }
            return Cursor((row,))
        if "FROM quality_runs" in sql:
            row = {"request_hash": digest("request"), "result_payload": None}
            return Cursor((row,))
        if "FROM quality_evidence" in sql:
            return Cursor()
        return Cursor()

    return respond


def finalize_delivery(repository: PostgresRevisionRepository):
    evidence = TransitionEvidence("run-1", "accepted", digest("certificate"))
    return repository.finalize_delivery(
        "job-1",
        "baseline",
        QualityState.ACCEPTED,
        evidence,
        b"certificate",
        result(DeliveryDecision.ACCEPT),
        run_id="run-1",
        request_hash=digest("request"),
        expected_version=3,
        commit_fence=fence(),
    )


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


def test_matching_run_and_transition_replays_do_not_write() -> None:
    transition = {
        "target_state": "LOGIC_REVIEWING",
        "source_state": "BASELINE_READY",
        "reason_code": "started",
        "evidence_hash": digest("transition"),
        "job_version": 1,
    }

    def respond(sql, parameters):
        if "FROM quality_runs" in sql:
            row = {"request_hash": digest("request"), "result_payload": None}
            return Cursor((row,))
        if "FROM quality_state_transitions" in sql:
            return Cursor((transition,))
        if "FROM quality_jobs" in sql:
            return Cursor((job_row(version=1, state="LOGIC_REVIEWING"),))
        return Cursor()

    connection = Connection(respond)
    repository = PostgresRevisionRepository(lambda: connection)
    repository.begin_run("job-1", "run-1", digest("request"))
    repository.transition_state(
        "job-1",
        QualityState.BASELINE_READY,
        QualityState.LOGIC_REVIEWING,
        TransitionEvidence("run-1", "started", digest("transition")),
        expected_version=0,
    )

    assert not any(_is_write(sql) for sql, _ in connection.executed)


def test_save_result_cas_race_rejects_different_persisted_result() -> None:
    saved = result(DeliveryDecision.HOLD).to_dict()
    rows = [
        {"request_hash": digest("request"), "result_payload": None},
        {"request_hash": digest("request"), "result_payload": saved},
    ]

    def respond(sql, parameters):
        if "FROM quality_runs" in sql:
            return Cursor((rows.pop(0),))
        if "UPDATE quality_runs" in sql:
            return Cursor(rowcount=0)
        return Cursor()

    connection = Connection(respond)
    repository = PostgresRevisionRepository(lambda: connection)

    with pytest.raises(DuplicateRunConflict, match="different result"):
        repository.save_run_result(
            "job-1",
            "run-1",
            digest("request"),
            result(DeliveryDecision.FAILED),
        )

    assert connection.events == ["BEGIN", "ROLLBACK"]


def test_append_cas_failure_is_typed_and_rolls_back() -> None:
    calls = 0

    def respond(sql, parameters):
        nonlocal calls
        if "FROM quality_revisions" in sql:
            calls += 1
            if calls == 1:
                return Cursor()
            row = {
                "job_id": "job-1",
                "parent_revision_id": None,
                "payload": baseline().to_dict(),
            }
            return Cursor((row,))
        if "FROM quality_jobs" in sql:
            return Cursor((job_row(version=2),))
        if "UPDATE quality_jobs" in sql:
            return Cursor(rowcount=0)
        return Cursor()

    connection = Connection(respond)
    repository = PostgresRevisionRepository(lambda: connection)
    payload = {
        **baseline().to_dict(),
        "revision_id": "child",
        "parent_revision_id": "baseline",
        "stage": "LOGIC_REPAIR",
    }
    child = baseline().from_dict(payload)

    with pytest.raises(StaleWrite):
        repository.append_revision("job-1", child, expected_version=0)

    assert connection.events == ["BEGIN", "ROLLBACK"]
    update = next(sql for sql, _ in connection.executed if "UPDATE quality_jobs" in sql)
    assert "version = %s" in update


def test_factory_exposes_revision_adapter_without_opening_connection() -> None:
    connections: list[str] = []

    factories = create_storage_factories(
        "postgresql://quality.example/platform",
        connector=lambda dsn: connections.append(dsn),
    )

    repository = factories.revision()
    assert isinstance(repository, RevisionRepository)
    assert isinstance(repository, PostgresRevisionRepository)
    assert connections == []


def test_postgres_adapters_do_not_import_sqlite_implementation_modules() -> None:
    root = Path(__file__).parents[3] / "src" / "manim_quality" / "storage" / "postgres"
    forbidden = (
        "manim_quality.storage._",
        "manim_quality.storage.intake",
        "manim_quality.storage.queue",
    )

    for path in root.glob("*.py"):
        modules = {
            node.module
            for node in ast.walk(ast.parse(path.read_text()))
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        assert not any(
            module.startswith(forbidden[0]) or module in forbidden[1:]
            for module in modules
        ), path


def _is_write(sql: str) -> bool:
    return sql.startswith(("INSERT", "UPDATE", "DELETE"))


def _index(statements: list[str], fragment: str) -> int:
    return next(i for i, sql in enumerate(statements) if fragment in sql)
