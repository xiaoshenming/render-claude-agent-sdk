"""SQLite transactional storage for immutable modification drafts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from manim_quality.contracts import QualityState, Revision
from manim_quality.storage._revision_records import revision_values
from manim_quality.storage._sqlite import open_sqlite, transaction

from . import sqlite_support as statements
from .codec import draft_from_row, sqlite_values
from .errors import ModificationConflict, ModificationNotFound, ModificationStale
from .models import ApprovalReceipt, DraftState, ModificationDraft


class SQLiteModificationRepository:
    def __init__(
        self,
        database: str | Path,
        approval_probe: Callable[[], None] | None = None,
    ) -> None:
        self._connection = open_sqlite(database)
        self._approval_probe = approval_probe

    def close(self) -> None:
        self._connection.close()

    def create(self, draft: ModificationDraft) -> ModificationDraft:
        with transaction(self._connection):
            existing = self._find_identity(draft)
            if existing is not None:
                stored = draft_from_row(existing)
                if stored.request_hash != draft.request_hash:
                    raise ModificationConflict("idempotency payload differs")
                return stored
            self._connection.execute(
                "INSERT INTO modification_drafts (draft_id, tenant_id, job_id, "
                "idempotency_key, request_hash, candidate_revision_id, state, "
                "version, quality_run_id, quality_job_id, payload) VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                sqlite_values(draft),
            )
        return draft

    def get(self, tenant_id: str, job_id: str, draft_id: str) -> ModificationDraft:
        row = self._connection.execute(
            "SELECT * FROM modification_drafts WHERE tenant_id=? AND job_id=? "
            "AND draft_id=?",
            (tenant_id, job_id, draft_id),
        ).fetchone()
        if row is None:
            raise ModificationNotFound(draft_id)
        return draft_from_row(row)

    def approve(
        self,
        draft: ModificationDraft,
        revision: Revision,
        quality_baseline: Revision,
        quality_job_id: str,
        queue_payload: bytes,
        queue_request_hash: str,
        stage_run_id: str,
        *,
        expected_version: int,
        now: datetime,
    ) -> ApprovalReceipt:
        timestamp = now.astimezone(UTC)
        with transaction(self._connection):
            current = self.get(draft.tenant_id, draft.job_id, draft.draft_id)
            if current.state is DraftState.APPROVED:
                if (
                    current.quality_run_id != stage_run_id
                    or current.quality_job_id != quality_job_id
                ):
                    raise ModificationConflict("draft approved with another run")
                return ApprovalReceipt(current, stage_run_id, quality_job_id)
            _require_transition(current, DraftState.PREVIEW_READY, expected_version)
            job = self._quality_job(draft.job_id)
            if QualityState(job["state"]) not in {
                QualityState.ACCEPTED,
                QualityState.ACCEPTED_WITH_WARNING,
            }:
                raise ModificationConflict("only accepted jobs may be modified")
            if revision.parent_revision_id != _current_parent(job):
                raise ModificationConflict("draft parent is no longer current")
            self._connection.execute(
                "INSERT INTO quality_revisions (revision_id, job_id, "
                "parent_revision_id, stage, payload, code_hash, "
                "semantic_fingerprint, render_manifest_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                revision_values(draft.job_id, revision),
            )
            self._advance_original_job(job)
            statements.create_quality_job(
                self._connection, quality_job_id, quality_baseline
            )
            if self._approval_probe is not None:
                self._approval_probe()
            statements.insert_queue(
                self._connection,
                draft,
                quality_job_id,
                queue_payload,
                queue_request_hash,
                stage_run_id,
                timestamp,
            )
            self._set_state(current, DraftState.APPROVED, stage_run_id, quality_job_id)
        approved = self.get(draft.tenant_id, draft.job_id, draft.draft_id)
        return ApprovalReceipt(approved, stage_run_id, quality_job_id)

    def discard(
        self,
        tenant_id: str,
        job_id: str,
        draft_id: str,
        *,
        expected_version: int,
    ) -> ModificationDraft:
        with transaction(self._connection):
            current = self.get(tenant_id, job_id, draft_id)
            if current.state is DraftState.DISCARDED:
                return current
            _require_transition(
                current,
                {DraftState.PREVIEW_READY, DraftState.FAILED},
                expected_version,
            )
            self._set_state(current, DraftState.DISCARDED, None, None)
        return self.get(tenant_id, job_id, draft_id)

    def _find_identity(self, draft: ModificationDraft):
        return self._connection.execute(
            "SELECT * FROM modification_drafts WHERE draft_id=? OR "
            "(tenant_id=? AND job_id=? AND idempotency_key=?)",
            (draft.draft_id, draft.tenant_id, draft.job_id, draft.idempotency_key),
        ).fetchone()

    def _quality_job(self, job_id: str):
        row = self._connection.execute(
            "SELECT * FROM quality_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise ModificationNotFound(job_id)
        return row

    def _advance_original_job(self, job) -> None:
        cursor = self._connection.execute(
            "UPDATE quality_jobs SET version=version+1 WHERE job_id=? AND version=?",
            (job["job_id"], job["version"]),
        )
        if cursor.rowcount != 1:
            raise ModificationStale("quality job changed during approval")

    def _set_state(
        self, draft, state: DraftState, run_id: str | None, quality_job_id: str | None
    ) -> None:
        cursor = self._connection.execute(
            "UPDATE modification_drafts SET state=?, version=version+1, "
            "quality_run_id=?, quality_job_id=?, "
            "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
            "WHERE draft_id=? AND version=?",
            (state.value, run_id, quality_job_id, draft.draft_id, draft.version),
        )
        if cursor.rowcount != 1:
            raise ModificationStale("draft changed concurrently")


def _require_transition(draft, expected_states, expected_version) -> None:
    states = expected_states if isinstance(expected_states, set) else {expected_states}
    if draft.state not in states:
        raise ModificationConflict(f"cannot transition {draft.state.value} draft")
    if draft.version != expected_version:
        raise ModificationStale("draft version is stale")


def _current_parent(job) -> str:
    return job["delivery_revision_id"] or job["render_baseline_revision_id"]
