from test_postgres_service_delivery_support import *

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
