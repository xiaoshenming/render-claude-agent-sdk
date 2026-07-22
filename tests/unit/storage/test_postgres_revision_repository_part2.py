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
