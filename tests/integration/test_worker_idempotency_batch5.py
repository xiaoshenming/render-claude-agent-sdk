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
def test_transition_replay_advanced_is_consumed_without_retry_or_hold(
    tmp_path: Path,
) -> None:
    from apps.worker.main import WorkerSettings, create_worker

    repository = seeded_repository(tmp_path)
    handler = Handler([TransitionReplayAdvanced("newer state exists")])
    holds = Holds()
    worker = create_worker(repository, handler, holds, WorkerSettings())

    assert worker.run_once("worker-a", now=utc()) is True
    assert repository.get(handler.calls[0]).state is QueueState.COMPLETED
    assert holds.calls == []
def test_long_handler_is_heartbeated_and_cannot_be_reclaimed(tmp_path: Path) -> None:
    from apps.worker.main import WorkerSettings, create_worker
    from manim_quality.worker.models import JobOutcome

    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(submission(), IntakeLimits(), deadline_for=timedelta(seconds=2))
    repository = SQLiteQueueRepository(database)
    reclaimed: list[object] = []

    class BlockingHandler:
        def handle(self, item):
            def contend() -> None:
                time.sleep(0.18)
                contender = SQLiteQueueRepository(database)
                reclaimed.append(
                    contender.claim(
                        QueueClass.QUALITY,
                        "worker-b",
                        now=datetime.now(UTC),
                        lease_for=timedelta(milliseconds=120),
                    )
                )
                contender.close()

            thread = threading.Thread(target=contend)
            thread.start()
            time.sleep(0.25)
            thread.join(timeout=1)
            return JobOutcome.completed()

    worker = create_worker(
        repository,
        BlockingHandler(),
        Holds(),
        WorkerSettings(
            lease_for=timedelta(milliseconds=120),
            heartbeat_interval=timedelta(milliseconds=30),
        ),
    )
    assert worker.run_once("worker-a") is True

    assert reclaimed == [None]
    assert repository.list_items(QueueClass.QUALITY)[0].state is QueueState.COMPLETED
def test_late_handler_result_uses_terminalization_not_completion(
    tmp_path: Path,
) -> None:
    from apps.worker.main import WorkerSettings, create_worker
    from manim_quality.worker.models import JobOutcome

    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(callback_url="https://callbacks.example/result"),
        IntakeLimits(),
        deadline_for=timedelta(milliseconds=80),
    )
    repository = SQLiteQueueRepository(database)

    class LateHandler:
        def handle(self, item):
            time.sleep(0.12)
            return JobOutcome.completed(b'{"state":"DELIVERED"}')

    worker = create_worker(
        repository,
        LateHandler(),
        Holds(),
        WorkerSettings(
            lease_for=timedelta(seconds=1),
            heartbeat_interval=timedelta(milliseconds=20),
        ),
    )

    assert worker.run_once("worker-a") is True
    source = repository.list_items(QueueClass.QUALITY)[0]

    assert source.state is QueueState.DEAD_LETTER
    assert source.terminal_reason == "DEADLINE_EXCEEDED"
    assert len(repository.list_items(QueueClass.HOLD)) == 1
    callbacks = repository.list_items(QueueClass.CALLBACK)
    assert len(callbacks) == 1
    assert b'"reason":"DEADLINE_EXCEEDED"' in callbacks[0].payload
def test_late_result_is_consumed_when_another_worker_terminalized(
    tmp_path: Path,
) -> None:
    from apps.worker.main import WorkerSettings, create_worker
    from manim_quality.worker.models import JobOutcome

    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(callback_url="https://callbacks.example/result"),
        IntakeLimits(),
        deadline_for=timedelta(milliseconds=50),
    )

    class RacingRepository(SQLiteQueueRepository):
        def terminalize_due(self, queue_class, *, now):
            raise AssertionError("late result must target its own lease")

    class LateHandler:
        def handle(self, item):
            time.sleep(0.08)
            return JobOutcome.completed()

    repository = RacingRepository(database)
    worker = create_worker(
        repository,
        LateHandler(),
        Holds(),
        WorkerSettings(
            lease_for=timedelta(seconds=1),
            heartbeat_interval=timedelta(milliseconds=20),
        ),
    )

    assert worker.run_once("worker-a") is True
    assert repository.list_items(QueueClass.QUALITY)[0].state is QueueState.DEAD_LETTER
    assert len(repository.list_items(QueueClass.HOLD)) == 1
    assert len(repository.list_items(QueueClass.CALLBACK)) == 1
def test_callback_queue_retries_separately_and_resolves_every_attempt(
    tmp_path: Path,
) -> None:
    from apps.worker.main import WorkerSettings, create_callback_worker

    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(callback_url="https://callbacks.example/result"),
        IntakeLimits(),
        now=utc(),
    )
    repository = SQLiteQueueRepository(database)
    quality = repository.claim(
        QueueClass.QUALITY, "quality-worker", now=utc(), lease_for=timedelta(seconds=5)
    )
    assert quality is not None
    repository.complete_terminal(quality, b"{}", now=utc())
    statuses = iter((503, 204))
    resolutions: list[str] = []
    requests: list[bytes] = []

    def resolver(hostname: str):
        resolutions.append(hostname)
        return ("93.184.216.34",)

    class Socket:
        def sendall(self, payload):
            requests.append(payload)

        def recv(self, size):
            status = next(statuses)
            return f"HTTP/1.1 {status} Result\r\n\r\n".encode()

        def close(self):
            pass

    class Tls:
        def wrap_socket(self, sock, *, server_hostname):
            return sock

    worker = create_callback_worker(
        repository,
        secret=b"runtime-secret",
        key_id="kid-1",
        resolver=resolver,
        socket_factory=lambda endpoint, timeout: Socket(),
        ssl_context=Tls(),
        timeout_seconds=3,
        settings=WorkerSettings(
            queue_class=QueueClass.CALLBACK,
            base_backoff=timedelta(seconds=1),
        ),
    )

    assert worker.run_once("callback-worker", now=utc()) is True
    retry_at = repository.list_items(QueueClass.CALLBACK)[0].available_at
    assert worker.run_once("callback-worker", now=retry_at) is True
    callback = repository.list_items(QueueClass.CALLBACK)[0]

    assert callback.state is QueueState.COMPLETED
    assert callback.attempt == 2
    assert callback.terminal_reason is None
    assert resolutions == ["callbacks.example", "callbacks.example"]
    assert (
        b"X-Quality-Event-Id: callback:" + quality.stage_run_id.encode() in requests[0]
    )
    assert (
        b"X-Quality-Event-Id: callback:" + quality.stage_run_id.encode() in requests[1]
    )
    assert (
        b"X-Quality-Delivery-Id: callback:" + quality.stage_run_id.encode() + b":1"
        in requests[0]
    )
    assert (
        b"X-Quality-Delivery-Id: callback:" + quality.stage_run_id.encode() + b":2"
        in requests[1]
    )
def test_callback_worker_factory_does_not_accept_transport_bypass() -> None:
    from apps.worker.main import create_callback_worker

    parameters = inspect.signature(create_callback_worker).parameters

    assert "transport" not in parameters
    assert {"socket_factory", "ssl_context", "timeout_seconds"} <= set(parameters)
def test_replay_claim_persists_across_repository_instances(tmp_path: Path) -> None:
    from manim_quality.storage.replay import SQLiteReplayRepository

    database = tmp_path / "replay.sqlite3"
    first = SQLiteReplayRepository(database)
    second = SQLiteReplayRepository(database)

    assert first.claim("event-1", expires_at=utc(300), now=utc()) is True
    assert second.claim("event-1", expires_at=utc(300), now=utc(1)) is False
