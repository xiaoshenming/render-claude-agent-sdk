"""Bounded queue execution without holding database leases open as transactions."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from manim_quality.revisions.store import TransitionReplayAdvanced
from manim_quality.storage.ports import QueueRepository
from manim_quality.storage.queue_models import QueueClass

from .ports import HoldHandler, JobHandler


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    queue_class: QueueClass = QueueClass.QUALITY
    lease_for: timedelta = timedelta(minutes=5)
    base_backoff: timedelta = timedelta(seconds=30)
    heartbeat_interval: timedelta = timedelta(minutes=1)


class QueueWorker:
    def __init__(
        self,
        repository: QueueRepository,
        handler: JobHandler,
        hold_handler: HoldHandler | None,
        settings: WorkerSettings,
    ) -> None:
        self._repository = repository
        self._handler = handler
        self._hold_handler = hold_handler
        self._settings = settings
        if settings.heartbeat_interval >= settings.lease_for:
            raise ValueError("heartbeat_interval must be shorter than lease_for")

    def run_once(self, owner: str, *, now: datetime | None = None) -> bool:
        origin = now or datetime.now(UTC)
        started = time.monotonic()

        def current() -> datetime:
            return origin + timedelta(seconds=time.monotonic() - started)

        lease = self._repository.claim(
            self._settings.queue_class,
            owner,
            now=origin,
            lease_for=self._settings.lease_for,
        )
        if lease is None:
            return self._repository.terminalize_due(
                self._settings.queue_class, now=origin
            )
        stop, heartbeat = self._start_heartbeat(lease, current)
        try:
            outcome = self._handler.handle(lease)
        except TransitionReplayAdvanced:
            stop.set()
            heartbeat.join()
            completed_at = current()
            if not self._terminalize_if_due(lease, completed_at):
                self._repository.complete(lease, now=completed_at)
            return True
        except Exception:
            stop.set()
            heartbeat.join()
            completed_at = current()
            if not self._terminalize_if_due(lease, completed_at):
                self._retry_or_exhaust(lease, completed_at)
            return True
        stop.set()
        heartbeat.join()
        completed_at = current()
        if not self._terminalize_if_due(lease, completed_at):
            self._repository.complete_terminal(
                lease, outcome.callback_body, now=completed_at
            )
        return True

    def _start_heartbeat(self, lease, current):
        stop = threading.Event()

        def run() -> None:
            repository = self._repository.fork()
            try:
                while not stop.wait(self._settings.heartbeat_interval.total_seconds()):
                    heartbeat_at = current()
                    if heartbeat_at >= lease.deadline:
                        return
                    repository.heartbeat(
                        lease, now=heartbeat_at, lease_for=self._settings.lease_for
                    )
            finally:
                repository.close()

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return stop, thread

    def _terminalize_if_due(self, lease, now: datetime) -> bool:
        if now < lease.deadline:
            return False
        self._repository.terminalize_lease(lease, now=now)
        return True

    def _retry_or_exhaust(self, lease, terminal_time: datetime) -> None:
        if lease.attempt >= lease.max_attempts:
            self._exhaust(lease, "INFRASTRUCTURE_EXHAUSTED", terminal_time)
            return
        delay = self._settings.base_backoff * (2 ** (lease.attempt - 1))
        available_at = terminal_time + delay
        if available_at >= lease.deadline:
            self._exhaust(lease, "DEADLINE_EXCEEDED", terminal_time)
            return
        self._repository.retry(
            lease,
            reason="INFRASTRUCTURE_RETRY",
            now=terminal_time,
            available_at=available_at,
        )

    def _exhaust(self, lease, reason: str, now: datetime) -> None:
        if lease.queue_class is QueueClass.QUALITY:
            body = json.dumps(
                {"job_id": lease.job_id, "reason": reason, "state": "HOLD"},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            self._repository.dead_letter_with_intents(lease, reason, body, now=now)
            return
        self._repository.dead_letter(lease, reason, now=now)
