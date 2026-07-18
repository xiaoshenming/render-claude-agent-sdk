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


@pytest.mark.parametrize("header", ["X-Quality-Event-Id", "X-Quality-Delivery-Id"])
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


@pytest.mark.parametrize(
    "url,addresses",
    [
        ("ftp://example.com/x", ("93.184.216.34",)),
        ("https://user@example.com/x", ("93.184.216.34",)),
        ("http://localhost/x", ("127.0.0.1",)),
        ("http://example.com/x", ("10.0.0.1",)),
        ("http://169.254.169.254/latest", ("169.254.169.254",)),
    ],
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


def test_pinned_transport_connects_validated_ip_with_host_and_tls_sni() -> None:
    from manim_quality.callbacks.pinned_transport import PinnedHttpTransport
    from manim_quality.callbacks.security import ResolvedDestination

    connections: list[tuple[tuple[str, int], float]] = []
    sent: list[bytes] = []
    sni: list[str] = []

    class Socket:
        def sendall(self, payload: bytes) -> None:
            sent.append(payload)

        def recv(self, size: int) -> bytes:
            return b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n"

        def close(self) -> None:
            pass

    class Tls:
        def wrap_socket(self, sock, *, server_hostname: str):
            sni.append(server_hostname)
            return sock

    def connect(address, timeout):
        connections.append((address, timeout))
        return Socket()

    transport = PinnedHttpTransport(
        socket_factory=connect,
        ssl_context=Tls(),
        timeout_seconds=3,
    )
    destination = ResolvedDestination(
        "https://callbacks.example/result?q=1",
        "callbacks.example",
        ("93.184.216.34",),
    )

    status = transport.send(destination, b"{}", {"X-Test": "value"})

    assert status == 204
    assert connections == [(("93.184.216.34", 443), 3)]
    assert sni == ["callbacks.example"]
    assert b"POST /result?q=1 HTTP/1.1\r\n" in sent[0]
    assert b"Host: callbacks.example\r\n" in sent[0]


@pytest.mark.parametrize(
    "url,hostname,address,expected_host,expected_sni",
    [
        (
            "https://callbacks.example/path",
            "callbacks.example",
            "93.184.216.34",
            b"Host: callbacks.example\r\n",
            "callbacks.example",
        ),
        (
            "https://callbacks.example:8443/path",
            "callbacks.example",
            "93.184.216.34",
            b"Host: callbacks.example:8443\r\n",
            "callbacks.example",
        ),
        (
            "https://[2001:4860:4860::8888]/path",
            "2001:4860:4860::8888",
            "2001:4860:4860::8888",
            b"Host: [2001:4860:4860::8888]\r\n",
            "2001:4860:4860::8888",
        ),
        (
            "https://[2001:4860:4860::8888]:8443/path",
            "2001:4860:4860::8888",
            "2001:4860:4860::8888",
            b"Host: [2001:4860:4860::8888]:8443\r\n",
            "2001:4860:4860::8888",
        ),
    ],
)
def test_pinned_transport_formats_host_authority_and_keeps_unbracketed_sni(
    url: str,
    hostname: str,
    address: str,
    expected_host: bytes,
    expected_sni: str,
) -> None:
    from manim_quality.callbacks.pinned_transport import PinnedHttpTransport
    from manim_quality.callbacks.security import ResolvedDestination

    sent: list[bytes] = []
    sni: list[str] = []

    class Socket:
        def sendall(self, payload: bytes) -> None:
            sent.append(payload)

        def recv(self, size: int) -> bytes:
            return b"HTTP/1.1 204 No Content\r\n\r\n"

        def close(self) -> None:
            pass

    class Tls:
        def wrap_socket(self, sock, *, server_hostname: str):
            sni.append(server_hostname)
            return sock

    transport = PinnedHttpTransport(
        socket_factory=lambda endpoint, timeout: Socket(),
        ssl_context=Tls(),
    )
    destination = ResolvedDestination(url, hostname, (address,))

    assert transport.send(destination, b"{}", {}) == 204
    assert expected_host in sent[0]
    assert sni == [expected_sni]


def test_unresolved_stale_orchestration_result_is_retried(tmp_path: Path) -> None:
    from apps.worker.main import WorkerSettings, create_worker

    repository = seeded_repository(tmp_path)
    handler = Handler([StaleWrite("job-1", 1, 2)])
    holds = Holds()
    worker = create_worker(repository, handler, holds, WorkerSettings())

    assert worker.run_once("worker-a", now=utc()) is True
    item = repository.get(handler.calls[0])

    assert item.state is QueueState.QUEUED
    assert item.attempt == 1
    assert item.heartbeat_at is not None
    assert item.available_at == item.heartbeat_at + timedelta(seconds=30)
    assert holds.calls == []


def test_expired_quality_lease_cannot_persist_terminal_result(tmp_path: Path) -> None:
    from dataclasses import replace

    from manim_quality.orchestrator.models import StageAction
    from manim_quality.revisions.store import CommitFence, CommitFenceRejected
    from manim_quality.storage.database import SQLiteRevisionRepository
    from tests.e2e.test_quality_happy_path import (
        baseline,
        execution_request,
        service,
    )

    database = tmp_path / "quality.sqlite3"
    now = datetime.now(UTC)
    SQLiteIntakeRepository(database).submit(
        submission(),
        IntakeLimits(),
        deadline_for=timedelta(milliseconds=50),
        now=now,
    )
    queue = SQLiteQueueRepository(database)
    lease = queue.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=now,
        lease_for=timedelta(seconds=1),
    )
    assert lease is not None
    revisions = SQLiteRevisionRepository(database)
    revisions.create_job("job-1", baseline())
    request = replace(
        execution_request(), run_id=lease.stage_run_id, request_hash=lease.request_hash
    )

    time.sleep(0.08)
    with pytest.raises(CommitFenceRejected):
        service(revisions, StageAction.CLEAN, StageAction.CLEAN).execute(
            request, commit_fence=CommitFence.from_queue_item(lease)
        )

    assert (
        revisions.get_run_result("job-1", request.run_id, request.request_hash) is None
    )


def test_reclaimed_quality_lease_rejects_old_worker_terminal_result(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from manim_quality.orchestrator.models import StageAction
    from manim_quality.revisions.store import CommitFence, CommitFenceRejected
    from manim_quality.storage.database import SQLiteRevisionRepository
    from tests.e2e.test_quality_happy_path import (
        baseline,
        execution_request,
        service,
    )

    database = tmp_path / "quality.sqlite3"
    now = datetime.now(UTC)
    SQLiteIntakeRepository(database).submit(
        submission(), IntakeLimits(), deadline_for=timedelta(hours=1), now=now
    )
    queue = SQLiteQueueRepository(database)
    old_lease = queue.claim(
        QueueClass.QUALITY,
        "worker-a",
        now=now,
        lease_for=timedelta(milliseconds=50),
    )
    assert old_lease is not None
    replacement = queue.claim(
        QueueClass.QUALITY,
        "worker-b",
        now=now + timedelta(milliseconds=60),
        lease_for=timedelta(seconds=1),
    )
    assert replacement is not None
    revisions = SQLiteRevisionRepository(database)
    revisions.create_job("job-1", baseline())
    request = replace(
        execution_request(),
        run_id=old_lease.stage_run_id,
        request_hash=old_lease.request_hash,
    )

    with pytest.raises(CommitFenceRejected):
        service(revisions, StageAction.CLEAN, StageAction.CLEAN).execute(
            request, commit_fence=CommitFence.from_queue_item(old_lease)
        )

    assert (
        revisions.get_run_result("job-1", request.run_id, request.request_hash) is None
    )


def test_quality_worker_threads_claimed_fence_into_orchestrator(
    tmp_path: Path,
) -> None:
    from dataclasses import replace

    from apps.worker.main import WorkerSettings, create_quality_worker
    from manim_quality.contracts import DeliveryDecision, QualityResult
    from manim_quality.orchestrator.models import OrchestrationResult
    from tests.e2e.test_quality_happy_path import execution_request

    repository = seeded_repository(tmp_path)
    observed = []

    class Orchestrator:
        def execute(self, request, *, commit_fence):
            observed.append((request, commit_fence))
            return OrchestrationResult(
                QualityResult(
                    request.job_id,
                    DeliveryDecision.HOLD,
                    None,
                    None,
                    None,
                    None,
                    (),
                    {},
                    {},
                ),
                object(),
            )

    def request_factory(item):
        return replace(
            execution_request(),
            run_id=item.stage_run_id,
            request_hash=item.request_hash,
        )

    worker = create_quality_worker(
        repository,
        Orchestrator(),
        request_factory,
        Holds(),
        WorkerSettings(),
    )

    assert worker.run_once("worker-a", now=utc()) is True
    request, fence = observed[0]
    completed = repository.get(request.run_id)

    assert fence.stage_run_id == request.run_id
    assert fence.lease_owner == "worker-a"
    assert fence.lease_token is not None
    assert fence.deadline == completed.deadline


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
