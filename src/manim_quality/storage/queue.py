"""CAS queue leases and bounded terminal transitions."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ._queue_outbox import (
    enqueue_callback,
    enqueue_hold,
    terminalize_due,
    terminalize_lease,
)
from ._sqlite import open_sqlite, transaction
from .errors import LeaseConflict, QueueItemNotFound
from .queue_models import IntakeLimits, QueueClass, QueueItem, QueueState


class SQLiteQueueRepository:
    def __init__(
        self,
        database: str | Path,
        terminal_probe: Callable[[], None] | None = None,
    ) -> None:
        self._database = database
        self._connection = open_sqlite(database)
        self._terminal_probe = terminal_probe

    def fork(self) -> SQLiteQueueRepository:
        return SQLiteQueueRepository(self._database)

    def close(self) -> None:
        self._connection.close()

    def claim(
        self,
        queue_class: QueueClass,
        owner: str,
        *,
        now: datetime,
        lease_for: timedelta,
    ) -> QueueItem | None:
        token = uuid.uuid4().hex
        with transaction(self._connection):
            row = self._connection.execute(
                "SELECT stage_run_id, deadline FROM quality_queue "
                "WHERE queue_class = ? AND "
                "attempt < max_attempts AND deadline > ? AND "
                "((state = 'QUEUED' AND available_at <= ?) OR "
                "(state = 'RUNNING' AND lease_expires_at <= ?)) "
                "ORDER BY available_at, stage_run_id LIMIT 1",
                (queue_class.value, _iso(now), _iso(now), _iso(now)),
            ).fetchone()
            if row is None:
                return None
            cursor = self._connection.execute(
                "UPDATE quality_queue SET state = 'RUNNING', attempt = attempt + 1, "
                "lease_owner = ?, lease_token = ?, lease_expires_at = ?, "
                "heartbeat_at = ? "
                "WHERE stage_run_id = ? AND attempt < max_attempts "
                "AND deadline > ? AND ((state = 'QUEUED' AND available_at <= ?) "
                "OR (state = 'RUNNING' AND lease_expires_at <= ?))",
                (
                    owner,
                    token,
                    _iso(min(now + lease_for, _time(row["deadline"]))),
                    _iso(now),
                    row["stage_run_id"],
                    _iso(now),
                    _iso(now),
                    _iso(now),
                ),
            )
            if cursor.rowcount != 1:
                return None
            return self.get(row["stage_run_id"])

    def heartbeat(
        self, lease: QueueItem, *, now: datetime, lease_for: timedelta
    ) -> QueueItem:
        expires_at = min(now + lease_for, lease.deadline)
        self._lease_update(
            lease,
            "heartbeat_at = ?, lease_expires_at = ?",
            (_iso(now), _iso(expires_at)),
            now=now,
        )
        return self.get(lease.stage_run_id)

    def complete(self, lease: QueueItem, *, now: datetime) -> QueueItem:
        self._lease_update(
            lease,
            "state = 'COMPLETED', heartbeat_at = ?, lease_expires_at = NULL",
            (_iso(now),),
            now=now,
        )
        return self.get(lease.stage_run_id)

    def complete_terminal(
        self, lease: QueueItem, callback_body: bytes | None, *, now: datetime
    ) -> QueueItem:
        with transaction(self._connection):
            self._lease_update(
                lease,
                "state = 'COMPLETED', heartbeat_at = ?, lease_expires_at = NULL",
                (_iso(now),),
                now=now,
            )
            if callback_body is not None:
                self.enqueue_callback(lease, callback_body, now=now)
        return self.get(lease.stage_run_id)

    def retry(
        self,
        lease: QueueItem,
        *,
        reason: str,
        now: datetime,
        available_at: datetime,
    ) -> QueueItem:
        self._lease_update(
            lease,
            "state = 'QUEUED', available_at = ?, terminal_reason = NULL, "
            "lease_owner = NULL, lease_token = NULL, lease_expires_at = NULL, "
            "heartbeat_at = ?",
            (_iso(available_at), _iso(now)),
            now=now,
        )
        return self.get(lease.stage_run_id)

    def dead_letter(self, lease: QueueItem, reason: str, *, now: datetime) -> QueueItem:
        self._lease_update(
            lease,
            "state = 'DEAD_LETTER', terminal_reason = ?, heartbeat_at = ?, "
            "lease_expires_at = NULL",
            (reason, _iso(now)),
            now=now,
            enforce_deadline=False,
        )
        return self.get(lease.stage_run_id)

    def dead_letter_with_intents(
        self,
        lease: QueueItem,
        reason: str,
        callback_body: bytes,
        *,
        now: datetime,
    ) -> QueueItem:
        with transaction(self._connection):
            self._dead_letter_update(lease, reason, now)
            if self._terminal_probe is not None:
                self._terminal_probe()
            enqueue_hold(self._connection, lease, reason, now)
            enqueue_callback(self._connection, lease, callback_body, now)
        return self.get(lease.stage_run_id)

    def terminalize_due(self, queue_class: QueueClass, *, now: datetime) -> bool:
        with transaction(self._connection):
            return terminalize_due(self._connection, queue_class, now, _item)

    def terminalize_lease(self, lease: QueueItem, *, now: datetime) -> None:
        with transaction(self._connection):
            terminalize_lease(self._connection, lease, now, _item)

    def enqueue_callback(
        self, source: QueueItem, body: bytes, *, now: datetime
    ) -> None:
        enqueue_callback(self._connection, source, body, now)

    def _dead_letter_update(self, lease: QueueItem, reason: str, now: datetime) -> None:
        self._lease_update(
            lease,
            "state = 'DEAD_LETTER', terminal_reason = ?, heartbeat_at = ?, "
            "lease_expires_at = NULL",
            (reason, _iso(now)),
            now=now,
            enforce_deadline=False,
        )

    def get(self, stage_run_id: str) -> QueueItem:
        row = self._connection.execute(
            "SELECT * FROM quality_queue WHERE stage_run_id = ?", (stage_run_id,)
        ).fetchone()
        if row is None:
            raise QueueItemNotFound(stage_run_id)
        return _item(row)

    def list_items(self, queue_class: QueueClass) -> tuple[QueueItem, ...]:
        rows = self._connection.execute(
            "SELECT * FROM quality_queue WHERE queue_class = ? ORDER BY stage_run_id",
            (queue_class.value,),
        ).fetchall()
        return tuple(_item(row) for row in rows)

    def _lease_update(
        self,
        lease: QueueItem,
        assignment: str,
        values: tuple,
        *,
        now: datetime,
        enforce_deadline: bool = True,
    ) -> None:
        deadline_clause = " AND deadline > ?" if enforce_deadline else ""
        cursor = self._connection.execute(
            f"UPDATE quality_queue SET {assignment} WHERE stage_run_id = ? "
            "AND state = 'RUNNING' AND lease_owner = ? AND lease_token = ? "
            f"AND lease_expires_at > ?{deadline_clause}",
            (
                *values,
                lease.stage_run_id,
                lease.lease_owner,
                lease.lease_token,
                _iso(now),
                *([_iso(now)] if enforce_deadline else []),
            ),
        )
        if cursor.rowcount != 1:
            raise LeaseConflict(lease.stage_run_id)


def _item(row: sqlite3.Row) -> QueueItem:
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
        available_at=_time(row["available_at"]),
        deadline=_time(row["deadline"]),
        lease_owner=row["lease_owner"],
        lease_token=row["lease_token"],
        lease_expires_at=_optional_time(row["lease_expires_at"]),
        heartbeat_at=_optional_time(row["heartbeat_at"]),
        terminal_reason=row["terminal_reason"],
        callback_url=row["callback_url"],
    )


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def _optional_time(value: str | None) -> datetime | None:
    return None if value is None else _time(value)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


__all__ = [
    "IntakeLimits",
    "LeaseConflict",
    "QueueClass",
    "QueueState",
    "SQLiteQueueRepository",
]
