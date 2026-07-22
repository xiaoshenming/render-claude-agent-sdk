from test_postgres_service_delivery_support import *

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
