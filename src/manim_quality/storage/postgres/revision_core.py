"""Production PostgreSQL RevisionRepository composition."""

from __future__ import annotations

from .revision_orchestration import PostgresRevisionOrchestrationMixin
from .revision_records import PostgresRevisionRecordsMixin
from .revision_terminal import PostgresRevisionTerminalMixin


class PostgresRevisionRepository(
    PostgresRevisionTerminalMixin,
    PostgresRevisionOrchestrationMixin,
    PostgresRevisionRecordsMixin,
):
    """Immutable, CAS-versioned, lease-fenced PostgreSQL repository."""

    def __init__(self, connection_factory) -> None:
        self._connection_factory = connection_factory

    def close(self) -> None:
        pass
