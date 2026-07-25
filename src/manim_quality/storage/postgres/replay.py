"""PostgreSQL persistent callback replay claims."""

from datetime import datetime


class PostgresReplayRepository:
    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    def close(self) -> None:
        pass

    def claim(self, event_id: str, *, expires_at: datetime, now: datetime) -> bool:
        if not event_id or expires_at <= now:
            return False
        connection = self._connection_factory()
        try:
            with connection.transaction():
                cursor = connection.execute(
                    """
                    WITH expired AS (
                        DELETE FROM callback_replays WHERE expires_at <= %s
                    )
                    INSERT INTO callback_replays (event_id, expires_at)
                    VALUES (%s, %s) ON CONFLICT (event_id) DO NOTHING
                    """,
                    (now, event_id, expires_at),
                )
                return cursor.rowcount == 1
        finally:
            connection.close()
