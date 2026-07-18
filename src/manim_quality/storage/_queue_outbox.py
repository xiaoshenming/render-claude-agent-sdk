"""SQLite queue outbox and due-terminalization operations."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from manim_quality.revisions.fingerprint import sha256_bytes

from .errors import LeaseConflict, QueueItemNotFound
from .queue_models import QueueClass, QueueItem


def enqueue_callback(connection, source: QueueItem, body: bytes, now: datetime) -> None:
    if source.callback_url is None:
        return
    connection.execute(
        "INSERT OR IGNORE INTO quality_queue (stage_run_id, tenant_id, job_id, "
        "queue_class, state, payload, request_hash, attempt, max_attempts, "
        "available_at, deadline, callback_url) VALUES (?, ?, ?, 'CALLBACK', "
        "'QUEUED', ?, ?, 0, 5, ?, ?, ?)",
        (
            f"callback:{source.stage_run_id}",
            source.tenant_id,
            source.job_id,
            body,
            sha256_bytes(body),
            _iso(now),
            _iso(now + timedelta(hours=24)),
            source.callback_url,
        ),
    )


def enqueue_hold(connection, source: QueueItem, reason: str, now: datetime) -> None:
    body = _body({"job_id": source.job_id, "reason": reason})
    connection.execute(
        "INSERT OR IGNORE INTO quality_queue (stage_run_id, tenant_id, job_id, "
        "queue_class, state, payload, request_hash, attempt, max_attempts, "
        "available_at, deadline) VALUES (?, ?, ?, 'HOLD', 'QUEUED', ?, ?, "
        "0, 5, ?, ?)",
        (
            f"hold:{source.stage_run_id}",
            source.tenant_id,
            source.job_id,
            body,
            sha256_bytes(body),
            _iso(now),
            _iso(now + timedelta(hours=2)),
        ),
    )


def terminalize_due(connection, queue_class, now, item_factory) -> bool:
    row = connection.execute(
        "SELECT * FROM quality_queue WHERE queue_class = ? AND "
        "((state = 'QUEUED' AND (deadline <= ? OR attempt >= max_attempts)) OR "
        "(state = 'RUNNING' AND lease_expires_at <= ? AND "
        "(deadline <= ? OR attempt >= max_attempts))) "
        "ORDER BY deadline, stage_run_id LIMIT 1",
        (queue_class.value, _iso(now), _iso(now), _iso(now)),
    ).fetchone()
    if row is None:
        return False
    item = item_factory(row)
    reason = "DEADLINE_EXCEEDED" if item.deadline <= now else "INFRASTRUCTURE_EXHAUSTED"
    connection.execute(
        "UPDATE quality_queue SET state = 'DEAD_LETTER', terminal_reason = ?, "
        "lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL "
        "WHERE stage_run_id = ? AND state IN ('QUEUED', 'RUNNING')",
        (reason, item.stage_run_id),
    )
    if queue_class is QueueClass.QUALITY:
        enqueue_hold(connection, item, reason, now)
        enqueue_callback(connection, item, terminal_body(item, reason), now)
    return True


def terminalize_lease(connection, lease, now, item_factory) -> None:
    row = connection.execute(
        "SELECT * FROM quality_queue WHERE stage_run_id = ?",
        (lease.stage_run_id,),
    ).fetchone()
    if row is None:
        raise QueueItemNotFound(lease.stage_run_id)
    current = item_factory(row)
    if current.state.value != "RUNNING":
        return
    if (
        current.lease_owner != lease.lease_owner
        or current.lease_token != lease.lease_token
    ):
        return
    if current.deadline > now:
        raise LeaseConflict(lease.stage_run_id)
    connection.execute(
        "UPDATE quality_queue SET state = 'DEAD_LETTER', "
        "terminal_reason = 'DEADLINE_EXCEEDED', lease_owner = NULL, "
        "lease_token = NULL, lease_expires_at = NULL "
        "WHERE stage_run_id = ? AND state = 'RUNNING' "
        "AND lease_owner = ? AND lease_token = ?",
        (lease.stage_run_id, lease.lease_owner, lease.lease_token),
    )
    if current.queue_class is QueueClass.QUALITY:
        enqueue_hold(connection, current, "DEADLINE_EXCEEDED", now)
        enqueue_callback(
            connection,
            current,
            terminal_body(current, "DEADLINE_EXCEEDED"),
            now,
        )


def terminal_body(item: QueueItem, reason: str) -> bytes:
    return _body({"job_id": item.job_id, "reason": reason, "state": "HOLD"})


def _body(value: dict[str, str]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
