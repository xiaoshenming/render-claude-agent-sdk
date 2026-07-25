from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from psycopg import OperationalError
from psycopg.errors import UniqueViolation

from apps.api.auth import GatewayHmacAuthenticator
from apps.api.main import ApiSettings, create_app
from apps.worker.main import WorkerSettings, create_worker
from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.storage.factory import StorageFactories, create_storage_factories
from manim_quality.storage.intake import IntakeLimits, IntakeTransactionError
from manim_quality.storage.postgres.common import canonical, queue_item
from manim_quality.storage.postgres.intake import PostgresIntakeRepository
from manim_quality.storage.postgres.queue import PostgresQueueRepository
from manim_quality.storage.postgres.reads import PostgresTenantReadRepository
from manim_quality.storage.postgres.replay import PostgresReplayRepository
from manim_quality.storage.queue import LeaseConflict
from manim_quality.storage.queue_models import (
    QueueClass,
    QueueState,
    SubmissionReceipt,
)
from tests.integration.test_api_jobs import submission
from tests.integration.test_worker_idempotency import utc


class Cursor:
    def __init__(self, rows=(), rowcount: int = 1) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return None if not self._rows else self._rows.pop(0)

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class Transaction:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        self.connection.events.append("BEGIN")
        return self

    def __exit__(self, error_type, error, traceback):
        self.connection.events.append("ROLLBACK" if error_type else "COMMIT")
        return False


class Connection:
    def __init__(self, responses=()) -> None:
        self.responses = list(responses)
        self.executed: list[tuple[str, object]] = []
        self.events: list[str] = []

    def transaction(self):
        return Transaction(self)

    def execute(self, sql: str, parameters=()):
        self.executed.append((" ".join(sql.split()), parameters))
        response = self.responses.pop(0) if self.responses else Cursor()
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        pass


def queue_row() -> dict[str, object]:
    return {
        "stage_run_id": "quality:job-1:hash",
        "tenant_id": "tenant-a",
        "job_id": "job-1",
        "queue_class": "QUALITY",
        "state": "QUEUED",
        "payload": b"{}",
        "request_hash": "sha256:" + "a" * 64,
        "attempt": 0,
        "max_attempts": 3,
        "available_at": utc(),
        "deadline": utc(300),
        "lease_owner": None,
        "lease_token": None,
        "lease_expires_at": None,
        "heartbeat_at": None,
        "terminal_reason": None,
        "callback_url": None,
    }


def test_postgres_claim_uses_skip_locked_and_fencing_update() -> None:
    row = queue_row()
    connection = Connection((Cursor((row,)), Cursor(({**row, "state": "RUNNING"},))))
    repository = PostgresQueueRepository(lambda: connection)

    claimed = repository.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=utc(),
        lease_for=timedelta(seconds=30),
    )

    assert claimed is not None
    assert "FOR UPDATE SKIP LOCKED" in connection.executed[0][0]
    assert "lease_token" in connection.executed[1][0]
    assert "deadline >" in connection.executed[0][0]
    assert "attempt < max_attempts" in connection.executed[0][0]


def test_postgres_replay_claim_is_unique_and_expiring() -> None:
    connection = Connection((Cursor(rowcount=1), Cursor(rowcount=0)))
    repository = PostgresReplayRepository(lambda: connection)

    first = repository.claim("event-1", expires_at=utc(300), now=utc())
    second = repository.claim("event-1", expires_at=utc(300), now=utc(1))

    assert first is True
    assert second is False
    assert all("ON CONFLICT" in sql for sql, _ in connection.executed)


def test_dsn_factory_exposes_postgres_without_opening_connection() -> None:
    connections: list[str] = []

    def connector(dsn: str):
        connections.append(dsn)
        return Connection()

    factories = create_storage_factories(
        "postgresql://quality.example/platform", connector=connector
    )

    assert factories.intake().__class__.__name__ == "PostgresIntakeRepository"
    assert factories.queue().__class__.__name__ == "PostgresQueueRepository"
    assert connections == []


def test_api_settings_exposes_production_dsn() -> None:
    settings = ApiSettings(storage_dsn="postgresql://quality.example/platform")

    assert settings.storage_dsn.startswith("postgresql://")


def test_postgres_intake_persists_submission_then_queue_in_one_transaction() -> None:
    connection = Connection(
        (
            Cursor(),
            Cursor(),
            Cursor(),
            Cursor(({"active": 0, "queued": 0},)),
            Cursor(),
            Cursor(),
        )
    )
    repository = PostgresIntakeRepository(lambda: connection)

    receipt = repository.submit(submission(), IntakeLimits(), now=utc())

    assert receipt.state is QueueState.QUEUED
    assert connection.events == ["BEGIN", "COMMIT"]
    sql = [statement for statement, _ in connection.executed]
    assert "INSERT INTO quality_submissions" in sql[4]
    assert "INSERT INTO quality_queue" in sql[5]


def test_postgres_intake_resolves_concurrent_idempotency_unique_race() -> None:
    body_hash = sha256_bytes(canonical(submission()))
    run_id = f"quality:job-1:{body_hash[7:23]}"
    racing = Connection(
        (
            Cursor(),
            Cursor(),
            Cursor(),
            Cursor(({"active": 0, "queued": 0},)),
            UniqueViolation(),
        )
    )
    resolved = Connection(
        (
            Cursor(),
            Cursor(
                (
                    {
                        "job_id": "job-1",
                        "stage_run_id": run_id,
                        "request_hash": body_hash,
                    },
                )
            ),
            Cursor(({"state": "QUEUED"},)),
        )
    )
    connections = iter((racing, resolved))
    repository = PostgresIntakeRepository(lambda: next(connections))

    receipt = repository.submit(submission(), IntakeLimits(), now=utc())

    assert receipt.stage_run_id == run_id
    assert racing.events == ["BEGIN", "ROLLBACK"]


def test_postgres_intake_maps_connection_failure_to_typed_error() -> None:
    def fail_connection():
        raise OperationalError("connection unavailable")

    repository = PostgresIntakeRepository(fail_connection)

    with pytest.raises(IntakeTransactionError, match="connection unavailable"):
        repository.submit(submission(), IntakeLimits(), now=utc())


def test_postgres_intake_maps_transaction_failure_to_typed_error() -> None:
    connection = Connection((OperationalError("database unavailable"),))
    repository = PostgresIntakeRepository(lambda: connection)

    with pytest.raises(IntakeTransactionError, match="database unavailable"):
        repository.submit(submission(), IntakeLimits(), now=utc())

    assert connection.events == ["BEGIN", "ROLLBACK"]


def test_postgres_tenant_reads_bind_owner_before_revision_query() -> None:
    connection = Connection(
        (
            Cursor(({"stage_run_id": "quality:job-1:hash"},)),
            Cursor(({"payload": {"revision_id": "rev-1"}},)),
        )
    )
    repository = PostgresTenantReadRepository(lambda: connection)

    revisions = repository.revisions("tenant-a", "job-1")

    assert revisions == [{"revision_id": "rev-1"}]
    assert connection.executed[0][1] == ("tenant-a", "job-1")
    assert "quality_submissions" in connection.executed[0][0]


def test_postgres_fenced_complete_rejects_stale_token() -> None:
    row = queue_row()
    row.update(
        state="RUNNING",
        lease_owner="worker-a",
        lease_token="token-a",
        lease_expires_at=utc(30),
    )
    repository = PostgresQueueRepository(lambda: Connection((Cursor(),)))

    with pytest.raises(LeaseConflict):
        repository.complete(
            queue_item(row),
            now=utc(1),
        )


def test_postgres_heartbeat_clamps_expiry_and_requires_deadline_future() -> None:
    row = queue_row()
    row.update(
        state="RUNNING",
        lease_owner="worker-a",
        lease_token="token-a",
        lease_expires_at=utc(30),
        deadline=utc(10),
    )
    renewed = {**row, "lease_expires_at": utc(10), "heartbeat_at": utc(4)}
    connection = Connection((Cursor((renewed,)),))
    repository = PostgresQueueRepository(lambda: connection)

    result = repository.heartbeat(
        queue_item(row), now=utc(4), lease_for=timedelta(seconds=20)
    )

    sql, parameters = connection.executed[0]
    assert result.lease_expires_at == utc(10)
    assert "deadline >" in sql
    assert parameters[1] == utc(10)


def test_postgres_complete_and_terminal_complete_require_deadline_future() -> None:
    row = queue_row()
    row.update(
        state="RUNNING",
        lease_owner="worker-a",
        lease_token="token-a",
        lease_expires_at=utc(10),
        deadline=utc(10),
    )
    first = Connection((Cursor(),))
    second = Connection((Cursor(),))
    connections = iter((first, second))
    repository = PostgresQueueRepository(lambda: next(connections))

    with pytest.raises(LeaseConflict):
        repository.complete(queue_item(row), now=utc(10))
    with pytest.raises(LeaseConflict):
        repository.complete_terminal(queue_item(row), b"{}", now=utc(10))

    assert "deadline >" in first.executed[0][0]
    assert "deadline >" in second.executed[0][0]


def test_postgres_dead_letter_and_outboxes_share_one_transaction() -> None:
    row = queue_row()
    row.update(
        state="RUNNING",
        lease_owner="worker-a",
        lease_token="token-a",
        lease_expires_at=utc(30),
        callback_url="https://callbacks.example/result",
    )
    dead = {**row, "state": "DEAD_LETTER"}
    connection = Connection((Cursor((dead,)), Cursor(), Cursor()))
    repository = PostgresQueueRepository(lambda: connection)
    repository.dead_letter_with_intents(
        queue_item(row), "INFRASTRUCTURE_EXHAUSTED", b"{}", now=utc(1)
    )

    assert connection.events == ["BEGIN", "COMMIT"]
    sql = [statement for statement, _ in connection.executed]
    assert "state='DEAD_LETTER'" in sql[0]
    assert "'HOLD'" in sql[1]
    assert "'CALLBACK'" in sql[2]


def test_postgres_terminalization_uses_skip_locked_and_outboxes() -> None:
    row = {**queue_row(), "deadline": utc(1), "callback_url": "https://cb.example"}
    connection = Connection((Cursor((row,)), Cursor(), Cursor(), Cursor()))
    repository = PostgresQueueRepository(lambda: connection)

    assert repository.terminalize_due(QueueClass.QUALITY, now=utc(2)) is True

    assert "FOR UPDATE SKIP LOCKED" in connection.executed[0][0]
    assert "'HOLD'" in connection.executed[2][0]
    assert "'CALLBACK'" in connection.executed[3][0]


def test_postgres_terminalizes_expired_running_lease_with_outboxes() -> None:
    row = {
        **queue_row(),
        "state": "RUNNING",
        "attempt": 3,
        "lease_owner": "dead-worker",
        "lease_token": "dead-token",
        "lease_expires_at": utc(1),
        "callback_url": "https://cb.example",
    }
    connection = Connection((Cursor((row,)), Cursor(), Cursor(), Cursor()))
    repository = PostgresQueueRepository(lambda: connection)

    assert repository.terminalize_due(QueueClass.QUALITY, now=utc(2)) is True

    select_sql = connection.executed[0][0]
    assert "state='RUNNING'" in select_sql
    assert "lease_expires_at <=" in select_sql
    assert connection.events == ["BEGIN", "COMMIT"]
    assert "'HOLD'" in connection.executed[2][0]
    assert "'CALLBACK'" in connection.executed[3][0]


def test_postgres_terminalizes_only_the_target_expired_lease() -> None:
    row = {
        **queue_row(),
        "state": "RUNNING",
        "attempt": 1,
        "deadline": utc(1),
        "lease_owner": "worker-a",
        "lease_token": "token-a",
        "lease_expires_at": utc(1),
        "callback_url": "https://cb.example",
    }
    connection = Connection((Cursor((row,)), Cursor(), Cursor(), Cursor()))
    repository = PostgresQueueRepository(lambda: connection)

    repository.terminalize_lease(queue_item(row), now=utc(2))

    assert "stage_run_id=%s FOR UPDATE" in connection.executed[0][0]
    assert connection.executed[0][1] == (row["stage_run_id"],)
    assert "state='DEAD_LETTER'" in connection.executed[1][0]
    assert "'HOLD'" in connection.executed[2][0]
    assert "'CALLBACK'" in connection.executed[3][0]
    assert connection.events == ["BEGIN", "COMMIT"]


def test_postgres_obsolete_lease_does_not_terminalize_new_owner() -> None:
    stale = {
        **queue_row(),
        "state": "RUNNING",
        "deadline": utc(1),
        "lease_owner": "worker-a",
        "lease_token": "token-a",
        "lease_expires_at": utc(1),
    }
    current = {**stale, "lease_owner": "worker-b", "lease_token": "token-b"}
    connection = Connection((Cursor((current,)),))
    repository = PostgresQueueRepository(lambda: connection)

    repository.terminalize_lease(queue_item(stale), now=utc(2))

    assert len(connection.executed) == 1
    assert connection.events == ["BEGIN", "COMMIT"]


def test_postgres_intake_locks_tenant_before_quota_and_inserts() -> None:
    connection = Connection(
        (
            Cursor(),
            Cursor(),
            Cursor(),
            Cursor(({"active": 0, "queued": 0},)),
            Cursor(),
            Cursor(),
        )
    )
    repository = PostgresIntakeRepository(lambda: connection)

    repository.submit(submission(), IntakeLimits(), now=utc())

    sql = [statement for statement, _ in connection.executed]
    lock_index = next(
        i for i, item in enumerate(sql) if "pg_advisory_xact_lock" in item
    )
    quota_index = next(i for i, item in enumerate(sql) if "COUNT(*) FILTER" in item)
    insert_index = next(
        i for i, item in enumerate(sql) if "INSERT INTO quality_submissions" in item
    )
    assert lock_index < quota_index < insert_index
    assert connection.events == ["BEGIN", "COMMIT"]


def test_api_uses_injected_repository_factories(tmp_path) -> None:
    received: list[dict[str, object]] = []

    class Intake:
        def submit(self, payload, limits, **kwargs):
            received.append(dict(payload))
            return SubmissionReceipt("job-1", "quality:job-1:hash", QueueState.QUEUED)

        def close(self):
            pass

    factories = StorageFactories(
        intake=Intake,
        reads=lambda: None,
        queue=lambda: None,
        replay=lambda: None,
        revision=lambda: None,
    )
    auth = GatewayHmacAuthenticator(b"runtime-test-secret", max_age_seconds=300)
    app = create_app(
        ApiSettings(database=tmp_path / "unused.sqlite3"),
        authenticator=auth,
        storage_factories=factories,
    )

    with TestClient(app) as client:
        response = client.post(
            "/v1/quality/jobs",
            headers=auth.headers("tenant-a"),
            json=submission(),
        )

    assert response.status_code == 202
    assert received[0]["tenant_id"] == "tenant-a"


def test_worker_accepts_queue_port_without_sqlite_concrete() -> None:
    class EmptyQueue:
        def claim(self, *args, **kwargs):
            return None

        def terminalize_due(self, *args, **kwargs):
            return False

    worker = create_worker(
        EmptyQueue(),
        object(),
        None,
        WorkerSettings(),
    )

    assert worker.run_once("worker-a", now=utc()) is False
