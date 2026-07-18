from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from manim_quality.contracts import (
    PatchScope,
    QualityState,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.modification.models import DraftState, ModificationDraft
from manim_quality.modification.postgres import PostgresModificationRepository
from manim_quality.revisions.fingerprint import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_bytes,
    sha256_text,
)

SOURCE = "class Lesson(Scene):\n    def construct(self):\n        self.add(Dot())\n"


def test_postgres_migration_defines_immutable_drafts_and_lookup() -> None:
    sql = Path("migrations/0004_user_modifications.sql").read_text(encoding="utf-8")
    lowered = sql.lower()

    assert "create table modification_drafts" in lowered
    assert "unique (tenant_id, job_id, idempotency_key)" in lowered
    assert "reject_modification_identity_update" in lowered
    assert "candidate_revision_id text not null unique" in lowered


def test_postgres_approval_locks_then_writes_one_transaction() -> None:
    draft = _draft()
    transaction = FakeConnection(
        preview_row=_row(draft),
        job_row=_job(),
        callback_row={"callback_url": None},
    )
    readback = FakeConnection(preview_row=_row(_approved(draft)))
    repository = PostgresModificationRepository(
        ConnectionFactory(transaction, readback)
    )

    receipt = repository.approve(
        draft,
        _revision(draft),
        _quality_baseline(draft, "job-1:mod:draft-1"),
        "job-1:mod:draft-1",
        b"{}",
        sha256_bytes(b"{}"),
        "quality:job-1:mod:draft-1",
        expected_version=0,
        now=datetime(2026, 7, 12, tzinfo=UTC),
    )

    sql = [statement.lower() for statement, _ in transaction.calls]
    assert receipt.draft.state is DraftState.APPROVED
    assert _index(sql, "from modification_drafts") < _index(sql, "from quality_jobs")
    assert _index(sql, "insert into quality_revisions") < _index(
        sql, "update quality_jobs"
    )
    assert _index(sql, "update quality_jobs") < _index(sql, "insert into quality_queue")
    assert _index(sql, "insert into quality_queue") < _index(
        sql, "update modification_drafts"
    )
    assert transaction.committed is True


def test_postgres_approval_probe_failure_rolls_back_before_queue() -> None:
    draft = _draft()
    connection = FakeConnection(
        preview_row=_row(draft),
        job_row=_job(),
        callback_row={"callback_url": None},
    )

    def fail() -> None:
        raise RuntimeError("injected failure")

    repository = PostgresModificationRepository(
        ConnectionFactory(connection), approval_probe=fail
    )
    with pytest.raises(RuntimeError, match="injected"):
        repository.approve(
            draft,
            _revision(draft),
            _quality_baseline(draft, "job-1:mod:draft-1"),
            "job-1:mod:draft-1",
            b"{}",
            sha256_bytes(b"{}"),
            "quality:job-1:mod:draft-1",
            expected_version=0,
            now=datetime(2026, 7, 12, tzinfo=UTC),
        )

    assert connection.rolled_back is True
    assert not any(
        "insert into quality_queue" in sql.lower() for sql, _ in connection.calls
    )


class Cursor:
    def __init__(self, row=None, rowcount: int = 1) -> None:
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class Transaction(AbstractContextManager):
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        del exc, traceback
        self.connection.committed = exc_type is None
        self.connection.rolled_back = exc_type is not None
        return False


class FakeConnection:
    def __init__(self, *, preview_row=None, job_row=None, callback_row=None) -> None:
        self.preview_row = preview_row
        self.job_row = job_row
        self.callback_row = callback_row
        self.calls: list[tuple[str, object]] = []
        self.committed = False
        self.rolled_back = False

    def transaction(self) -> Transaction:
        return Transaction(self)

    def execute(self, sql: str, parameters=None) -> Cursor:
        self.calls.append((sql, parameters))
        lowered = sql.lower()
        if "from modification_drafts" in lowered:
            return Cursor(self.preview_row)
        if "from quality_jobs" in lowered:
            return Cursor(self.job_row)
        if "select q.callback_url" in lowered:
            return Cursor(self.callback_row)
        return Cursor()

    def close(self) -> None:
        pass


class ConnectionFactory:
    def __init__(self, *connections: FakeConnection) -> None:
        self.connections = list(connections)

    def __call__(self) -> FakeConnection:
        return self.connections.pop(0)


def _draft() -> ModificationDraft:
    candidate = SOURCE.replace("Dot()", "Dot(LEFT)")
    return ModificationDraft(
        "draft-1",
        "tenant-a",
        "job-1",
        "idem-1",
        sha256_text("request"),
        "baseline-1",
        "user-mod-1",
        "Move the dot.",
        ("Lesson",),
        candidate,
        sha256_text("preview"),
        sha256_text("video"),
        DraftState.PREVIEW_READY,
    )


def _revision(draft: ModificationDraft) -> Revision:
    return Revision(
        draft.candidate_revision_id,
        draft.parent_revision_id,
        RevisionStage.USER_MODIFICATION,
        code_hash(draft.candidate_source),
        semantic_fingerprint(draft.candidate_source),
        scene_fingerprints(draft.candidate_source),
        None,
        draft.target_scene_ids,
        PatchScope.USER_SCENES,
        RevisionCreator.USER,
        1,
    )


def _quality_baseline(draft: ModificationDraft, job_id: str) -> Revision:
    return Revision(
        f"baseline-{job_id}",
        None,
        RevisionStage.BASELINE,
        code_hash(draft.candidate_source),
        semantic_fingerprint(draft.candidate_source),
        scene_fingerprints(draft.candidate_source),
        draft.preview_manifest_hash,
        (),
        PatchScope.FULL_CANDIDATE,
        RevisionCreator.USER,
        0,
    )


def _row(draft: ModificationDraft) -> dict[str, object]:
    from manim_quality.modification.codec import draft_payload

    return {
        "draft_id": draft.draft_id,
        "tenant_id": draft.tenant_id,
        "job_id": draft.job_id,
        "idempotency_key": draft.idempotency_key,
        "request_hash": draft.request_hash,
        "candidate_revision_id": draft.candidate_revision_id,
        "state": draft.state.value,
        "version": draft.version,
        "quality_run_id": draft.quality_run_id,
        "quality_job_id": draft.quality_job_id,
        "payload": draft_payload(draft),
    }


def _approved(draft: ModificationDraft) -> ModificationDraft:
    from dataclasses import replace

    return replace(
        draft,
        state=DraftState.APPROVED,
        version=1,
        quality_run_id="quality:job-1:mod:draft-1",
        quality_job_id="job-1:mod:draft-1",
    )


def _job() -> dict[str, object]:
    return {
        "job_id": "job-1",
        "version": 7,
        "state": QualityState.ACCEPTED.value,
        "delivery_revision_id": None,
        "render_baseline_revision_id": "baseline-1",
    }


def _index(statements: list[str], fragment: str) -> int:
    return next(index for index, sql in enumerate(statements) if fragment in sql)
