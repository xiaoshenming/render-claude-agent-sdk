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
