from __future__ import annotations

import inspect
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from manim_quality.revisions.store import StaleWrite, TransitionReplayAdvanced
from manim_quality.storage.intake import IntakeLimits, SQLiteIntakeRepository
from manim_quality.storage.queue import (
    LeaseConflict,
    QueueClass,
    QueueState,
    SQLiteQueueRepository,
)

from .test_api_jobs import submission


def utc(second: int = 0) -> datetime:
    return datetime(2026, 7, 11, 8, 0, tzinfo=UTC) + timedelta(seconds=second)


def seeded_repository(
    tmp_path: Path,
    *,
    attempts: int = 3,
    deadline_for: timedelta = timedelta(hours=2),
) -> SQLiteQueueRepository:
    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(),
        IntakeLimits(),
        max_attempts=attempts,
        deadline_for=deadline_for,
        now=utc(),
    )
    return SQLiteQueueRepository(database)


@dataclass
class Handler:
    outcomes: list[object]
    calls: list[str] = field(default_factory=list)

    def handle(self, item):
        self.calls.append(item.stage_run_id)
        value = self.outcomes.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


@dataclass
class Holds:
    calls: list[tuple[str, str]] = field(default_factory=list)

    def hold(self, job_id: str, reason: str, stage_run_id: str = "test") -> None:
        self.calls.append((job_id, reason))
def test_atomic_claim_and_duplicate_worker_is_idempotent(tmp_path: Path) -> None:
    from apps.worker.main import WorkerSettings, create_worker
    from manim_quality.worker.models import JobOutcome

    repository = seeded_repository(tmp_path)
    handler = Handler([JobOutcome.completed()])
    worker = create_worker(repository, handler, Holds(), WorkerSettings())

    first = worker.run_once("worker-a", now=utc())
    second = worker.run_once("worker-b", now=utc(1))

    assert first is True
    assert second is False
    assert len(handler.calls) == 1
    assert repository.get(handler.calls[0]).state is QueueState.COMPLETED
def test_expired_lease_recovers_and_stale_worker_is_rejected(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path)
    first = repository.claim(
        QueueClass.QUALITY, "worker-a", now=utc(), lease_for=timedelta(seconds=5)
    )
    assert first is not None
    recovered = repository.claim(
        QueueClass.QUALITY, "worker-b", now=utc(6), lease_for=timedelta(seconds=5)
    )
    assert recovered is not None
    assert recovered.stage_run_id == first.stage_run_id
    assert recovered.lease_token != first.lease_token

    with pytest.raises(LeaseConflict):
        repository.heartbeat(first, now=utc(7), lease_for=timedelta(seconds=5))
    with pytest.raises(LeaseConflict):
        repository.complete(first, now=utc(7))
def test_expired_lease_cannot_heartbeat_or_complete_before_reclaim(
    tmp_path: Path,
) -> None:
    repository = seeded_repository(tmp_path)
    lease = repository.claim(
        QueueClass.QUALITY, "worker-a", now=utc(), lease_for=timedelta(seconds=5)
    )
    assert lease is not None

    with pytest.raises(LeaseConflict):
        repository.heartbeat(lease, now=utc(6), lease_for=timedelta(seconds=5))
    with pytest.raises(LeaseConflict):
        repository.complete(lease, now=utc(6))
def test_heartbeat_clamps_lease_to_hard_deadline(tmp_path: Path) -> None:
    repository = seeded_repository(tmp_path, deadline_for=timedelta(seconds=10))
    lease = repository.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=utc(),
        lease_for=timedelta(seconds=5),
    )
    assert lease is not None

    renewed = repository.heartbeat(
        lease,
        now=utc(4),
        lease_for=timedelta(seconds=20),
    )

    assert renewed.lease_expires_at == utc(10)
    with pytest.raises(LeaseConflict):
        repository.heartbeat(
            renewed,
            now=utc(10),
            lease_for=timedelta(seconds=1),
        )
def test_late_completion_rejected_then_atomically_terminalized(tmp_path: Path) -> None:
    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(callback_url="https://callbacks.example/result"),
        IntakeLimits(),
        deadline_for=timedelta(seconds=1),
        now=utc(),
    )
    repository = SQLiteQueueRepository(database)
    lease = repository.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=utc(),
        lease_for=timedelta(seconds=30),
    )
    assert lease is not None
    assert lease.lease_expires_at == utc(1)

    with pytest.raises(LeaseConflict):
        repository.complete(lease, now=utc(1))
    with pytest.raises(LeaseConflict):
        repository.complete_terminal(lease, b"{}", now=utc(1))

    assert repository.terminalize_due(QueueClass.QUALITY, now=utc(1)) is True
    assert repository.get(lease.stage_run_id).state is QueueState.DEAD_LETTER
    assert len(repository.list_items(QueueClass.HOLD)) == 1
    assert len(repository.list_items(QueueClass.CALLBACK)) == 1
def test_retry_exhaustion_atomically_enqueues_durable_hold(tmp_path: Path) -> None:
    from apps.worker.main import WorkerSettings, create_hold_worker, create_worker

    repository = seeded_repository(tmp_path, attempts=2)
    handler = Handler([RuntimeError("infra"), RuntimeError("infra")])
    holds = Holds()
    settings = WorkerSettings(base_backoff=timedelta(seconds=1))
    worker = create_worker(repository, handler, holds, settings)

    assert worker.run_once("worker-a", now=utc()) is True
    retry_at = repository.list_items(QueueClass.QUALITY)[0].available_at
    assert worker.run_once("worker-a", now=retry_at) is True
    item = repository.get(handler.calls[0])

    assert item.state is QueueState.DEAD_LETTER
    assert item.terminal_reason == "INFRASTRUCTURE_EXHAUSTED"
    assert holds.calls == []
    hold_items = repository.list_items(QueueClass.HOLD)
    assert len(hold_items) == 1
    hold_worker = create_hold_worker(repository, holds, WorkerSettings())
    assert hold_worker.run_once("hold-worker", now=utc(2)) is True
    assert holds.calls == [(item.job_id, "INFRASTRUCTURE_EXHAUSTED")]
def test_retry_backoff_starts_after_failure_completion(tmp_path: Path) -> None:
    from apps.worker.main import WorkerSettings, create_worker

    repository = seeded_repository(tmp_path)

    class SlowFailure:
        def handle(self, item):
            time.sleep(0.05)
            raise RuntimeError("infra")

    worker = create_worker(
        repository,
        SlowFailure(),
        Holds(),
        WorkerSettings(base_backoff=timedelta(seconds=1)),
    )

    assert worker.run_once("worker-a", now=utc()) is True
    item = repository.list_items(QueueClass.QUALITY)[0]

    assert item.heartbeat_at is not None
    assert item.available_at == item.heartbeat_at + timedelta(seconds=1)
def test_deadline_exhaustion_does_not_invoke_handler(tmp_path: Path) -> None:
    from apps.worker.main import WorkerSettings, create_worker
    from manim_quality.worker.models import JobOutcome

    repository = seeded_repository(tmp_path, deadline_for=timedelta(seconds=1))
    item = repository.claim(
        QueueClass.QUALITY, "worker-a", now=utc(), lease_for=timedelta(seconds=1)
    )
    assert item is not None
    repository.retry(
        item,
        reason="infra",
        now=utc(),
        available_at=utc(1),
    )
    handler = Handler([JobOutcome.completed()])
    holds = Holds()
    worker = create_worker(repository, handler, holds, WorkerSettings())

    assert worker.run_once("worker-b", now=utc(2)) is True
    assert handler.calls == []
    assert holds.calls == []
    assert len(repository.list_items(QueueClass.HOLD)) == 1
def test_claim_excludes_deadline_and_attempt_exhausted_work(tmp_path: Path) -> None:
    expired = seeded_repository(tmp_path, deadline_for=timedelta(seconds=1))
    assert (
        expired.claim(
            QueueClass.QUALITY,
            "worker-a",
            now=utc(2),
            lease_for=timedelta(seconds=1),
        )
        is None
    )
    item = expired.list_items(QueueClass.QUALITY)[0]
    expired._connection.execute(  # type: ignore[attr-defined]
        "UPDATE quality_queue SET attempt = max_attempts WHERE stage_run_id = ?",
        (item.stage_run_id,),
    )
    assert (
        expired.claim(
            QueueClass.QUALITY,
            "worker-b",
            now=utc(),
            lease_for=timedelta(seconds=1),
        )
        is None
    )
def test_expired_running_terminalizes_with_atomic_hold_and_callback(
    tmp_path: Path,
) -> None:
    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(callback_url="https://callbacks.example/result"),
        IntakeLimits(),
        max_attempts=1,
        deadline_for=timedelta(seconds=30),
        now=utc(),
    )
    repository = SQLiteQueueRepository(database)
    lease = repository.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=utc(),
        lease_for=timedelta(seconds=1),
    )
    assert lease is not None

    assert repository.terminalize_due(QueueClass.QUALITY, now=utc(2)) is True

    source = repository.get(lease.stage_run_id)
    assert source.state is QueueState.DEAD_LETTER
    assert source.terminal_reason == "INFRASTRUCTURE_EXHAUSTED"
    assert len(repository.list_items(QueueClass.HOLD)) == 1
    assert len(repository.list_items(QueueClass.CALLBACK)) == 1
