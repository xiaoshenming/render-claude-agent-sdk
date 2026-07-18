"""Shared PostgreSQL encoding helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from manim_quality.storage.queue_models import QueueClass, QueueItem, QueueState


def queue_item(row) -> QueueItem:
    return QueueItem(
        stage_run_id=row["stage_run_id"],
        tenant_id=row["tenant_id"],
        job_id=row["job_id"],
        queue_class=QueueClass(row["queue_class"]),
        state=QueueState(row["state"]),
        payload=bytes(row["payload"]),
        request_hash=row["request_hash"],
        attempt=row["attempt"],
        max_attempts=row["max_attempts"],
        available_at=as_utc(row["available_at"]),
        deadline=as_utc(row["deadline"]),
        lease_owner=row["lease_owner"],
        lease_token=row["lease_token"],
        lease_expires_at=optional_utc(row["lease_expires_at"]),
        heartbeat_at=optional_utc(row["heartbeat_at"]),
        terminal_reason=row["terminal_reason"],
        callback_url=row["callback_url"],
    )


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


def optional_utc(value: datetime | None) -> datetime | None:
    return None if value is None else as_utc(value)
