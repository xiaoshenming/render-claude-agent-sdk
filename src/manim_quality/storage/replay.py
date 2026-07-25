"""Persistent callback replay claims."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ._sqlite import open_sqlite, transaction


class ReplayRepository(Protocol):
    def claim(self, event_id: str, *, expires_at: datetime, now: datetime) -> bool: ...


class SQLiteReplayRepository:
    def __init__(self, database: str | Path) -> None:
        self._connection = open_sqlite(database)

    def close(self) -> None:
        self._connection.close()

    def claim(self, event_id: str, *, expires_at: datetime, now: datetime) -> bool:
        if not event_id or expires_at <= now:
            return False
        with transaction(self._connection):
            self._connection.execute(
                "DELETE FROM callback_replays WHERE expires_at <= ?", (_iso(now),)
            )
            try:
                self._connection.execute(
                    "INSERT INTO callback_replays (event_id, expires_at) VALUES (?, ?)",
                    (event_id, _iso(expires_at)),
                )
            except sqlite3.IntegrityError:
                return False
        return True


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
