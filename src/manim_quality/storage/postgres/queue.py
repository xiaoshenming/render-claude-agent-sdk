"""PostgreSQL queue with SKIP LOCKED claims and fenced leases."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from manim_quality.storage.errors import LeaseConflict, QueueItemNotFound
from manim_quality.storage.queue_models import QueueClass, QueueItem

from .common import queue_item
from .outbox import enqueue_callback, enqueue_hold, terminal_body


class PostgresQueueRepository:
    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    def fork(self) -> PostgresQueueRepository:
        return PostgresQueueRepository(self._connection_factory)

    def close(self) -> None:
        pass

    def claim(
        self,
        queue_class: QueueClass,
        owner: str,
        *,
        now: datetime,
        lease_for: timedelta,
    ) -> QueueItem | None:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                row = connection.execute(
                    "SELECT * FROM quality_queue WHERE queue_class = %s "
                    "AND attempt < max_attempts AND deadline > %s AND "
                    "((state = 'QUEUED' AND available_at <= %s) OR "
                    "(state = 'RUNNING' AND lease_expires_at <= %s)) "
                    "ORDER BY available_at, stage_run_id "
                    "FOR UPDATE SKIP LOCKED LIMIT 1",
                    (queue_class.value, now, now, now),
                ).fetchone()
                if row is None:
                    return None
                token = uuid.uuid4().hex
                claimed = connection.execute(
                    "UPDATE quality_queue SET state='RUNNING', attempt=attempt+1, "
                    "lease_owner=%s, lease_token=%s, lease_expires_at=%s, "
                    "heartbeat_at=%s "
                    "WHERE stage_run_id=%s RETURNING *",
                    (
                        owner,
                        token,
                        min(now + lease_for, row["deadline"]),
                        now,
                        row["stage_run_id"],
                    ),
                ).fetchone()
                return queue_item(claimed)
        finally:
            connection.close()

    def heartbeat(
        self, lease: QueueItem, *, now: datetime, lease_for: timedelta
    ) -> QueueItem:
        expires_at = min(now + lease_for, lease.deadline)
        return self._lease_update(
            lease,
            "heartbeat_at=%s, lease_expires_at=%s",
            (now, expires_at),
            now,
        )

    def complete(self, lease: QueueItem, *, now: datetime) -> QueueItem:
        return self._lease_update(
            lease,
            "state='COMPLETED', heartbeat_at=%s, lease_expires_at=NULL",
            (now,),
            now,
        )

    def complete_terminal(
        self, lease: QueueItem, callback_body: bytes | None, *, now: datetime
    ) -> QueueItem:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                item = self._lease_update_on(
                    connection,
                    lease,
                    "state='COMPLETED', heartbeat_at=%s, lease_expires_at=NULL",
                    (now,),
                    now,
                )
                if callback_body is not None:
                    enqueue_callback(connection, lease, callback_body, now)
                return item
        finally:
            connection.close()

    def retry(
        self,
        lease: QueueItem,
        *,
        reason: str,
        now: datetime,
        available_at: datetime,
    ) -> QueueItem:
        return self._lease_update(
            lease,
            "state='QUEUED', available_at=%s, terminal_reason=NULL, "
            "lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL, "
            "heartbeat_at=%s",
            (available_at, now),
            now,
        )

    def dead_letter(self, lease: QueueItem, reason: str, *, now: datetime) -> QueueItem:
        return self._lease_update(
            lease,
            "state='DEAD_LETTER', terminal_reason=%s, heartbeat_at=%s, "
            "lease_expires_at=NULL",
            (reason, now),
            now,
        )

    def dead_letter_with_intents(
        self, lease: QueueItem, reason: str, callback_body: bytes, *, now: datetime
    ) -> QueueItem:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                item = self._lease_update_on(
                    connection,
                    lease,
                    "state='DEAD_LETTER', terminal_reason=%s, heartbeat_at=%s, "
                    "lease_expires_at=NULL",
                    (reason, now),
                    now,
                )
                enqueue_hold(connection, lease, reason, now)
                enqueue_callback(connection, lease, callback_body, now)
                return item
        finally:
            connection.close()

    def terminalize_due(self, queue_class: QueueClass, *, now: datetime) -> bool:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                row = connection.execute(
                    "SELECT * FROM quality_queue WHERE queue_class=%s "
                    "AND ((state='QUEUED' AND "
                    "(deadline <= %s OR attempt >= max_attempts)) OR "
                    "(state='RUNNING' AND lease_expires_at <= %s AND "
                    "(deadline <= %s OR attempt >= max_attempts))) "
                    "ORDER BY deadline, stage_run_id FOR UPDATE SKIP LOCKED LIMIT 1",
                    (queue_class.value, now, now, now),
                ).fetchone()
                if row is None:
                    return False
                item = queue_item(row)
                reason = (
                    "DEADLINE_EXCEEDED"
                    if item.deadline <= now
                    else "INFRASTRUCTURE_EXHAUSTED"
                )
                connection.execute(
                    "UPDATE quality_queue SET state='DEAD_LETTER', terminal_reason=%s, "
                    "lease_owner=NULL, lease_token=NULL, lease_expires_at=NULL "
                    "WHERE stage_run_id=%s",
                    (reason, item.stage_run_id),
                )
                if queue_class is QueueClass.QUALITY:
                    enqueue_hold(connection, item, reason, now)
                    enqueue_callback(connection, item, terminal_body(item, reason), now)
                return True
        finally:
            connection.close()

    def terminalize_lease(self, lease: QueueItem, *, now: datetime) -> None:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                row = connection.execute(
                    "SELECT * FROM quality_queue WHERE stage_run_id=%s FOR UPDATE",
                    (lease.stage_run_id,),
                ).fetchone()
                if row is None:
                    raise QueueItemNotFound(lease.stage_run_id)
                current = queue_item(row)
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
                    "UPDATE quality_queue SET state='DEAD_LETTER', "
                    "terminal_reason='DEADLINE_EXCEEDED', lease_owner=NULL, "
                    "lease_token=NULL, lease_expires_at=NULL "
                    "WHERE stage_run_id=%s AND state='RUNNING' "
                    "AND lease_owner=%s AND lease_token=%s",
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
        finally:
            connection.close()

    def get(self, stage_run_id: str) -> QueueItem:
        connection = self._connection_factory()
        try:
            row = connection.execute(
                "SELECT * FROM quality_queue WHERE stage_run_id=%s", (stage_run_id,)
            ).fetchone()
            if row is None:
                raise QueueItemNotFound(stage_run_id)
            return queue_item(row)
        finally:
            connection.close()

    def list_items(self, queue_class: QueueClass) -> tuple[QueueItem, ...]:
        connection = self._connection_factory()
        try:
            rows = connection.execute(
                "SELECT * FROM quality_queue WHERE queue_class=%s "
                "ORDER BY stage_run_id",
                (queue_class.value,),
            ).fetchall()
            return tuple(queue_item(row) for row in rows)
        finally:
            connection.close()

    def _lease_update(self, lease, assignment, values, now) -> QueueItem:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                return self._lease_update_on(connection, lease, assignment, values, now)
        finally:
            connection.close()

    @staticmethod
    def _lease_update_on(
        connection,
        lease,
        assignment,
        values,
        now,
        *,
        enforce_deadline: bool = True,
    ) -> QueueItem:
        deadline_clause = " AND deadline > %s" if enforce_deadline else ""
        row = connection.execute(
            f"UPDATE quality_queue SET {assignment} WHERE stage_run_id=%s "
            "AND state='RUNNING' AND lease_owner=%s AND lease_token=%s "
            f"AND lease_expires_at > %s{deadline_clause} RETURNING *",
            (
                *values,
                lease.stage_run_id,
                lease.lease_owner,
                lease.lease_token,
                now,
                *([now] if enforce_deadline else []),
            ),
        ).fetchone()
        if row is None:
            raise LeaseConflict(lease.stage_run_id)
        return queue_item(row)
