"""PostgreSQL HOLD and callback outbox inserts."""

from __future__ import annotations

import json
from datetime import timedelta

from manim_quality.revisions.fingerprint import sha256_bytes
from manim_quality.storage.queue_models import QueueItem


def enqueue_hold(connection, source: QueueItem, reason: str, now) -> None:
    body = _body({"job_id": source.job_id, "reason": reason})
    connection.execute(
        "INSERT INTO quality_queue (stage_run_id, tenant_id, job_id, queue_class, "
        "state, payload, request_hash, attempt, max_attempts, available_at, deadline) "
        "VALUES (%s,%s,%s,'HOLD','QUEUED',%s,%s,0,5,%s,%s) "
        "ON CONFLICT (stage_run_id) DO NOTHING",
        (
            f"hold:{source.stage_run_id}",
            source.tenant_id,
            source.job_id,
            body,
            sha256_bytes(body),
            now,
            now + timedelta(hours=2),
        ),
    )


def enqueue_callback(connection, source: QueueItem, body: bytes, now) -> None:
    if source.callback_url is None:
        return
    connection.execute(
        "INSERT INTO quality_queue (stage_run_id, tenant_id, job_id, queue_class, "
        "state, payload, request_hash, attempt, max_attempts, available_at, "
        "deadline, callback_url) VALUES "
        "(%s,%s,%s,'CALLBACK','QUEUED',%s,%s,0,5,%s,%s,%s) "
        "ON CONFLICT (stage_run_id) DO NOTHING",
        (
            f"callback:{source.stage_run_id}",
            source.tenant_id,
            source.job_id,
            body,
            sha256_bytes(body),
            now,
            now + timedelta(hours=24),
            source.callback_url,
        ),
    )


def terminal_body(source: QueueItem, reason: str) -> bytes:
    return _body({"job_id": source.job_id, "reason": reason, "state": "HOLD"})


def _body(value: dict[str, str]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
