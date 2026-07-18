"""SQLite connection, schema, and rollback helpers for the local adapter."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from manim_quality.revisions.store import RepositoryError, RepositoryTransactionError

from ._modification_schema import MODIFICATION_SCHEMA
from ._service_schema import SERVICE_DELIVERY_SCHEMA

_SCHEMA_LOCK = threading.Lock()

SQLITE_SCHEMA = (
    """
CREATE TABLE IF NOT EXISTS quality_jobs (
    job_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version >= 0),
    state TEXT NOT NULL,
    render_baseline_revision_id TEXT NOT NULL,
    logic_certified_revision_id TEXT,
    layout_certified_revision_id TEXT,
    delivery_revision_id TEXT,
    render_baseline_evidence_hash TEXT CHECK (
        render_baseline_evidence_hash IS NULL OR (
            length(render_baseline_evidence_hash) = 71 AND
            substr(render_baseline_evidence_hash, 1, 7) = 'sha256:' AND
            substr(render_baseline_evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    logic_certified_evidence_hash TEXT CHECK (
        logic_certified_evidence_hash IS NULL OR (
            length(logic_certified_evidence_hash) = 71 AND
            substr(logic_certified_evidence_hash, 1, 7) = 'sha256:' AND
            substr(logic_certified_evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    layout_certified_evidence_hash TEXT CHECK (
        layout_certified_evidence_hash IS NULL OR (
            length(layout_certified_evidence_hash) = 71 AND
            substr(layout_certified_evidence_hash, 1, 7) = 'sha256:' AND
            substr(layout_certified_evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    delivery_evidence_hash TEXT CHECK (
        delivery_evidence_hash IS NULL OR (
            length(delivery_evidence_hash) = 71 AND
            substr(delivery_evidence_hash, 1, 7) = 'sha256:' AND
            substr(delivery_evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (job_id, render_baseline_revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (job_id, logic_certified_revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (job_id, layout_certified_revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (job_id, delivery_revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS quality_revisions (
    revision_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    parent_revision_id TEXT,
    stage TEXT NOT NULL,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    code_hash TEXT NOT NULL CHECK (
        length(code_hash) = 71 AND substr(code_hash, 1, 7) = 'sha256:' AND
        substr(code_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    semantic_fingerprint TEXT NOT NULL CHECK (
        length(semantic_fingerprint) = 71 AND
        substr(semantic_fingerprint, 1, 7) = 'sha256:' AND
        substr(semantic_fingerprint, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    render_manifest_hash TEXT CHECK (
        render_manifest_hash IS NULL OR (
            length(render_manifest_hash) = 71 AND
            substr(render_manifest_hash, 1, 7) = 'sha256:' AND
            substr(render_manifest_hash, 8) NOT GLOB '*[^0-9a-f]*'
        )
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (job_id, revision_id),
    FOREIGN KEY (job_id) REFERENCES quality_jobs(job_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (job_id, parent_revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    CHECK (
        (parent_revision_id IS NULL AND stage = 'BASELINE') OR
        (parent_revision_id IS NOT NULL AND stage <> 'BASELINE')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS one_revision_root_per_job
ON quality_revisions(job_id) WHERE parent_revision_id IS NULL;

CREATE TABLE IF NOT EXISTS quality_checkpoint_history (
    job_id TEXT NOT NULL,
    checkpoint TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    evidence_hash TEXT NOT NULL CHECK (
        length(evidence_hash) = 71 AND
        substr(evidence_hash, 1, 7) = 'sha256:' AND
        substr(evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    job_version INTEGER NOT NULL CHECK (job_version >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (job_id, checkpoint, job_version),
    FOREIGN KEY (job_id, revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS quality_state_transitions (
    job_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    evidence_hash TEXT NOT NULL CHECK (
        length(evidence_hash) = 71 AND
        substr(evidence_hash, 1, 7) = 'sha256:' AND
        substr(evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    source_state TEXT NOT NULL,
    target_state TEXT NOT NULL,
    job_version INTEGER NOT NULL CHECK (job_version >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (job_id, run_id),
    FOREIGN KEY (job_id) REFERENCES quality_jobs(job_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS quality_runs (
    job_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (
        length(request_hash) = 71 AND
        substr(request_hash, 1, 7) = 'sha256:' AND
        substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    result_payload TEXT CHECK (result_payload IS NULL OR json_valid(result_payload)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (job_id, run_id),
    FOREIGN KEY (job_id) REFERENCES quality_jobs(job_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS quality_evidence (
    evidence_hash TEXT PRIMARY KEY CHECK (
        length(evidence_hash) = 71 AND
        substr(evidence_hash, 1, 7) = 'sha256:' AND
        substr(evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    payload BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS quality_rollbacks (
    job_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    rollback_to_revision_id TEXT NOT NULL,
    failed_revision_id TEXT,
    reason_code TEXT NOT NULL,
    evidence_hash TEXT NOT NULL CHECK (
        length(evidence_hash) = 71 AND
        substr(evidence_hash, 1, 7) = 'sha256:' AND
        substr(evidence_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    job_version INTEGER NOT NULL CHECK (job_version >= 0),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (job_id, run_id),
    FOREIGN KEY (job_id, rollback_to_revision_id)
        REFERENCES quality_revisions(job_id, revision_id) ON DELETE RESTRICT,
    FOREIGN KEY (job_id, failed_revision_id)
        REFERENCES quality_revisions(job_id, revision_id) ON DELETE RESTRICT
);

CREATE TRIGGER IF NOT EXISTS reject_quality_revision_update
BEFORE UPDATE ON quality_revisions
BEGIN
    SELECT RAISE(ABORT, 'quality revisions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_quality_revision_delete
BEFORE DELETE ON quality_revisions
BEGIN
    SELECT RAISE(ABORT, 'quality revisions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_checkpoint_history_update
BEFORE UPDATE ON quality_checkpoint_history
BEGIN
    SELECT RAISE(ABORT, 'checkpoint history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_checkpoint_history_delete
BEFORE DELETE ON quality_checkpoint_history
BEGIN
    SELECT RAISE(ABORT, 'checkpoint history is immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_state_transition_update
BEFORE UPDATE ON quality_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'state transitions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_state_transition_delete
BEFORE DELETE ON quality_state_transitions
BEGIN
    SELECT RAISE(ABORT, 'state transitions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_evidence_update
BEFORE UPDATE ON quality_evidence
BEGIN
    SELECT RAISE(ABORT, 'quality evidence is immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_evidence_delete
BEFORE DELETE ON quality_evidence
BEGIN
    SELECT RAISE(ABORT, 'quality evidence is immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_rollback_update
BEFORE UPDATE ON quality_rollbacks
BEGIN
    SELECT RAISE(ABORT, 'quality rollbacks are immutable');
END;

CREATE TRIGGER IF NOT EXISTS reject_rollback_delete
BEFORE DELETE ON quality_rollbacks
BEGIN
    SELECT RAISE(ABORT, 'quality rollbacks are immutable');
END;

"""
    + SERVICE_DELIVERY_SCHEMA
    + MODIFICATION_SCHEMA
)


def open_sqlite(database: str | Path) -> sqlite3.Connection:
    location = str(database)
    connection = sqlite3.connect(location, isolation_level=None, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    with _SCHEMA_LOCK:
        if location != ":memory:":
            connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(SQLITE_SCHEMA)
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[None]:
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except RepositoryError:
        connection.rollback()
        raise
    except sqlite3.DatabaseError as error:
        connection.rollback()
        raise RepositoryTransactionError(str(error)) from error
    except BaseException:
        connection.rollback()
        raise
