"""Lazy SQLite/PostgreSQL service-delivery repository factories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from manim_quality.modification.ports import ModificationRepository
from manim_quality.revisions.store import RevisionRepository

from .database import SQLiteRevisionRepository
from .intake import SQLiteIntakeRepository
from .ports import (
    IntakeRepository,
    QueueRepository,
    ReplayRepository,
    TenantReadRepository,
)
from .queue import SQLiteQueueRepository
from .reads import SQLiteTenantReadRepository
from .replay import SQLiteReplayRepository


@dataclass(frozen=True, slots=True)
class StorageFactories:
    intake: Callable[[], IntakeRepository]
    reads: Callable[[], TenantReadRepository]
    queue: Callable[[], QueueRepository]
    replay: Callable[[], ReplayRepository]
    revision: Callable[[], RevisionRepository]
    modification: Callable[[], ModificationRepository] | None = None


def create_storage_factories(
    target: str | Path,
    *,
    connector=None,
    publication_probe=None,
) -> StorageFactories:
    if isinstance(target, Path) or not str(target).startswith("postgres"):
        path = _sqlite_path(target)
        return StorageFactories(
            intake=lambda: SQLiteIntakeRepository(path, publication_probe),
            reads=lambda: SQLiteTenantReadRepository(path),
            queue=lambda: SQLiteQueueRepository(path),
            replay=lambda: SQLiteReplayRepository(path),
            revision=lambda: SQLiteRevisionRepository(path),
            modification=lambda: _sqlite_modification(path),
        )
    connection_factory = _connection_factory(str(target), connector)
    from .postgres import (
        PostgresIntakeRepository,
        PostgresQueueRepository,
        PostgresReplayRepository,
        PostgresRevisionRepository,
        PostgresTenantReadRepository,
    )

    return StorageFactories(
        intake=lambda: PostgresIntakeRepository(connection_factory, publication_probe),
        reads=lambda: PostgresTenantReadRepository(connection_factory),
        queue=lambda: PostgresQueueRepository(connection_factory),
        replay=lambda: PostgresReplayRepository(connection_factory),
        revision=lambda: PostgresRevisionRepository(connection_factory),
        modification=lambda: _postgres_modification(connection_factory),
    )


def _sqlite_modification(path):
    from manim_quality.modification.repository import SQLiteModificationRepository

    return SQLiteModificationRepository(path)


def _postgres_modification(connection_factory):
    from manim_quality.modification.postgres import PostgresModificationRepository

    return PostgresModificationRepository(connection_factory)


def _connection_factory(dsn: str, connector):
    def connect():
        if connector is not None:
            return connector(dsn)
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(dsn, row_factory=dict_row)

    return connect


def _sqlite_path(target: str | Path) -> str | Path:
    if isinstance(target, Path):
        return target
    if target.startswith("sqlite:///"):
        return target.removeprefix("sqlite:///")
    return target
