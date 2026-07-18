"""Service-delivery persistence ports used by API and workers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol

from .queue_models import (
    IntakeLimits,
    QueueClass,
    QueueItem,
    SubmissionReceipt,
)


class IntakeRepository(Protocol):
    def submit(
        self,
        payload: Mapping[str, object],
        limits: IntakeLimits,
        *,
        max_attempts: int = 3,
        deadline_for: timedelta = timedelta(hours=2),
        now: datetime | None = None,
    ) -> SubmissionReceipt: ...

    def close(self) -> None: ...


class TenantReadRepository(Protocol):
    def job(self, tenant_id: str, job_id: str) -> dict[str, object]: ...

    def revisions(self, tenant_id: str, job_id: str) -> list[dict[str, object]]: ...

    def evidence_hashes(self, tenant_id: str, job_id: str) -> list[str]: ...

    def certificate(self, tenant_id: str, job_id: str) -> tuple[str, bytes] | None: ...

    def close(self) -> None: ...


class QueueRepository(Protocol):
    def fork(self) -> QueueRepository: ...

    def claim(
        self,
        queue_class: QueueClass,
        owner: str,
        *,
        now: datetime,
        lease_for: timedelta,
    ) -> QueueItem | None: ...

    def heartbeat(
        self, lease: QueueItem, *, now: datetime, lease_for: timedelta
    ) -> QueueItem: ...

    def complete(self, lease: QueueItem, *, now: datetime) -> QueueItem: ...

    def complete_terminal(
        self, lease: QueueItem, callback_body: bytes | None, *, now: datetime
    ) -> QueueItem: ...

    def retry(
        self,
        lease: QueueItem,
        *,
        reason: str,
        now: datetime,
        available_at: datetime,
    ) -> QueueItem: ...

    def dead_letter(
        self, lease: QueueItem, reason: str, *, now: datetime
    ) -> QueueItem: ...

    def dead_letter_with_intents(
        self, lease: QueueItem, reason: str, callback_body: bytes, *, now: datetime
    ) -> QueueItem: ...

    def terminalize_due(self, queue_class: QueueClass, *, now: datetime) -> bool: ...

    def terminalize_lease(self, lease: QueueItem, *, now: datetime) -> None: ...

    def close(self) -> None: ...


class ReplayRepository(Protocol):
    def claim(self, event_id: str, *, expires_at: datetime, now: datetime) -> bool: ...

    def close(self) -> None: ...
