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
def test_terminal_failure_rolls_back_without_hold_and_callback_intents(
    tmp_path: Path,
) -> None:
    database = tmp_path / "quality.sqlite3"
    intake = SQLiteIntakeRepository(database)
    intake.submit(
        submission(callback_url="https://callbacks.example/result"),
        IntakeLimits(),
        now=utc(),
    )

    def crash() -> None:
        raise RuntimeError("injected terminal crash")

    repository = SQLiteQueueRepository(database, terminal_probe=crash)
    lease = repository.claim(
        QueueClass.QUALITY, "worker", now=utc(), lease_for=timedelta(seconds=5)
    )
    assert lease is not None

    with pytest.raises(RuntimeError, match="terminal crash"):
        repository.dead_letter_with_intents(
            lease, "INFRASTRUCTURE_EXHAUSTED", b'{"state":"HOLD"}', now=utc()
        )

    assert repository.get(lease.stage_run_id).state is QueueState.RUNNING
    assert repository.list_items(QueueClass.HOLD) == ()
    assert repository.list_items(QueueClass.CALLBACK) == ()
def test_queue_identity_is_database_immutable(tmp_path: Path) -> None:
    import sqlite3

    repository = seeded_repository(tmp_path)
    item = repository.list_items(QueueClass.QUALITY)[0]

    with pytest.raises(sqlite3.IntegrityError):
        repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE quality_queue SET deadline = ? WHERE stage_run_id = ?",
            (utc(10).isoformat(), item.stage_run_id),
        )
    with pytest.raises(sqlite3.IntegrityError):
        repository._connection.execute(  # type: ignore[attr-defined]
            "UPDATE quality_queue SET request_hash = ? WHERE stage_run_id = ?",
            ("sha256:" + "a" * 64, item.stage_run_id),
        )
def test_terminal_outcome_persists_callback_task(tmp_path: Path) -> None:
    from apps.worker.main import WorkerSettings, create_worker
    from manim_quality.worker.models import JobOutcome

    database = tmp_path / "quality.sqlite3"
    payload = submission(callback_url="https://callbacks.example/result")
    intake = SQLiteIntakeRepository(database)
    receipt = intake.submit(payload, IntakeLimits(), now=utc())
    repository = SQLiteQueueRepository(database)
    handler = Handler([JobOutcome.completed(b'{"state":"DELIVERED"}')])
    worker = create_worker(repository, handler, Holds(), WorkerSettings())

    assert worker.run_once("worker-a", now=utc()) is True
    callbacks = repository.list_items(QueueClass.CALLBACK)

    assert len(callbacks) == 1
    assert callbacks[0].job_id == receipt.job_id
    assert callbacks[0].request_hash.startswith("sha256:")
def test_callback_retry_delivery_identity_rejects_replay_and_allows_next_attempt(
    tmp_path: Path,
) -> None:
    from manim_quality.callbacks.delivery import CallbackDispatcher
    from manim_quality.callbacks.security import (
        CallbackSecurityError,
        verify_callback_signature,
    )
    from manim_quality.storage.replay import SQLiteReplayRepository

    body = b'{"state":"DELIVERED"}'
    first_headers = CallbackDispatcher.sign(
        body, b"runtime-secret", "kid-1", "event-1", "event-1:1", utc()
    )
    retry_headers = CallbackDispatcher.sign(
        body, b"runtime-secret", "kid-1", "event-1", "event-1:2", utc(1)
    )
    replay = SQLiteReplayRepository(tmp_path / "replay.sqlite3")

    verify_callback_signature(
        body, first_headers, {"kid-1": b"runtime-secret"}, utc(1), replay
    )
    with pytest.raises(CallbackSecurityError, match="replayed"):
        verify_callback_signature(
            body, first_headers, {"kid-1": b"runtime-secret"}, utc(1), replay
        )

    verify_callback_signature(
        body, retry_headers, {"kid-1": b"runtime-secret"}, utc(2), replay
    )

    assert first_headers["X-Quality-Event-Id"] == "event-1"
    assert retry_headers["X-Quality-Event-Id"] == "event-1"
    assert first_headers["X-Quality-Delivery-Id"] == "event-1:1"
    assert retry_headers["X-Quality-Delivery-Id"] == "event-1:2"
def test_callback_signature_binds_event_and_delivery_identity(
    tmp_path: Path, header: str
) -> None:
    from manim_quality.callbacks.delivery import CallbackDispatcher
    from manim_quality.callbacks.security import (
        CallbackSecurityError,
        verify_callback_signature,
    )
    from manim_quality.storage.replay import SQLiteReplayRepository

    body = b'{"state":"DELIVERED"}'
    headers = CallbackDispatcher.sign(
        body, b"runtime-secret", "kid-1", "event-1", "event-1:1", utc()
    )
    headers[header] = "tampered"

    with pytest.raises(CallbackSecurityError, match="invalid callback signature"):
        verify_callback_signature(
            body,
            headers,
            {"kid-1": b"runtime-secret"},
            utc(1),
            SQLiteReplayRepository(tmp_path / f"{header}.sqlite3"),
        )
def test_callback_signature_fails_closed_without_delivery_identity(
    tmp_path: Path,
) -> None:
    from manim_quality.callbacks.delivery import CallbackDispatcher
    from manim_quality.callbacks.security import (
        CallbackSecurityError,
        verify_callback_signature,
    )
    from manim_quality.storage.replay import SQLiteReplayRepository

    body = b'{"state":"DELIVERED"}'
    headers = CallbackDispatcher.sign(
        body, b"runtime-secret", "kid-1", "event-1", "event-1:1", utc()
    )
    del headers["X-Quality-Delivery-Id"]

    with pytest.raises(CallbackSecurityError, match="signature headers"):
        verify_callback_signature(
            body,
            headers,
            {"kid-1": b"runtime-secret"},
            utc(1),
            SQLiteReplayRepository(tmp_path / "missing.sqlite3"),
        )
def test_callback_signature_rejects_body_and_expired_timestamp(tmp_path: Path) -> None:
    from manim_quality.callbacks.delivery import CallbackDispatcher
    from manim_quality.callbacks.security import (
        CallbackSecurityError,
        verify_callback_signature,
    )
    from manim_quality.storage.replay import SQLiteReplayRepository

    body = b'{"state":"DELIVERED"}'
    headers = CallbackDispatcher.sign(
        body, b"runtime-secret", "kid-1", "event-1", "event-1:1", utc()
    )
    replay = SQLiteReplayRepository(tmp_path / "replay-invalid.sqlite3")

    with pytest.raises(CallbackSecurityError):
        verify_callback_signature(
            body + b" ", headers, {"kid-1": b"runtime-secret"}, utc(1), replay
        )
    with pytest.raises(CallbackSecurityError):
        verify_callback_signature(
            body, headers, {"kid-1": b"runtime-secret"}, utc(400), replay
        )
def test_callback_destination_blocks_ssrf(url: str, addresses: tuple[str, ...]) -> None:
    from manim_quality.callbacks.security import (
        CallbackSecurityError,
        ResolvedDestination,
    )

    with pytest.raises(CallbackSecurityError):
        ResolvedDestination.resolve(url, lambda _: addresses)
def test_callback_rejects_any_unsafe_ip_and_dns_failure() -> None:
    from manim_quality.callbacks.security import (
        CallbackSecurityError,
        ResolvedDestination,
    )

    with pytest.raises(CallbackSecurityError):
        ResolvedDestination.resolve(
            "https://example.com/x", lambda _: ("93.184.216.34", "127.0.0.1")
        )
    with pytest.raises(CallbackSecurityError):
        ResolvedDestination.resolve(
            "https://example.com/x", lambda _: (_ for _ in ()).throw(OSError())
        )
def test_callback_dispatch_uses_injected_transport_and_no_network() -> None:
    from manim_quality.callbacks.delivery import CallbackDispatcher, CallbackOutcome

    sent = []

    class Transport:
        def send(self, destination, body, headers) -> int:
            sent.append((destination, body, headers))
            return 204

    dispatcher = CallbackDispatcher(
        secret=b"runtime-secret",
        key_id="kid-1",
        resolver=lambda _: ("93.184.216.34",),
        transport=Transport(),
    )
    with pytest.raises(ValueError):
        dispatcher.deliver("https://callbacks.example/result", b"{}", now=utc())
    outcome = dispatcher.deliver(
        "https://callbacks.example/result",
        b"{}",
        now=utc(),
        event_id="event-1",
        delivery_id="event-1:1",
    )

    assert outcome is CallbackOutcome.DELIVERED
    assert sent[0][0].url == "https://callbacks.example/result"
    assert sent[0][0].addresses == ("93.184.216.34",)
