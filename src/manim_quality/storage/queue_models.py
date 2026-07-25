"""Immutable queue contracts shared by intake, workers, and callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class QueueClass(StrEnum):
    QUALITY = "QUALITY"
    CALLBACK = "CALLBACK"
    HOLD = "HOLD"


class QueueState(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    DEAD_LETTER = "DEAD_LETTER"


@dataclass(frozen=True, slots=True)
class QueueItem:
    stage_run_id: str
    tenant_id: str
    job_id: str
    queue_class: QueueClass
    state: QueueState
    payload: bytes
    request_hash: str
    attempt: int
    max_attempts: int
    available_at: datetime
    deadline: datetime
    lease_owner: str | None = None
    lease_token: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    terminal_reason: str | None = None
    callback_url: str | None = None


@dataclass(frozen=True, slots=True)
class SubmissionReceipt:
    job_id: str
    stage_run_id: str
    state: QueueState
    schema_version: int = 1

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "stage_run_id": self.stage_run_id,
            "queue_state": self.state.value,
        }


@dataclass(frozen=True, slots=True)
class IntakeLimits:
    max_active_jobs: int = 100
    max_queued_jobs: int = 100
