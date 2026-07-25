"""PostgreSQL transactional storage for user modification drafts."""

from __future__ import annotations

from collections.abc import Callable

from psycopg import Error
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from manim_quality.revisions.store import RepositoryTransactionError

from . import postgres_support as sql
from .codec import draft_from_row, draft_payload
from .errors import ModificationConflict, ModificationNotFound, ModificationStale
from .models import ApprovalReceipt, DraftState, ModificationDraft


class PostgresModificationRepository:
    def __init__(
        self,
        connection_factory,
        approval_probe: Callable[[], None] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._approval_probe = approval_probe

    def close(self) -> None:
        pass

    def create(self, draft: ModificationDraft) -> ModificationDraft:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                sql.lock_tenant(connection, draft.tenant_id)
                row = sql.find_identity(connection, draft)
                if row is not None:
                    stored = draft_from_row(row)
                    if stored.request_hash != draft.request_hash:
                        raise ModificationConflict("idempotency payload differs")
                    return stored
                connection.execute(
                    "INSERT INTO modification_drafts (draft_id,tenant_id,job_id,"
                    "idempotency_key,request_hash,candidate_revision_id,state,"
                    "version,quality_run_id,quality_job_id,payload) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    _values(draft),
                )
            return draft
        except UniqueViolation as error:
            del error
            return self._resolve_create_race(draft)
        except Error as error:
            raise RepositoryTransactionError(str(error)) from error
        finally:
            connection.close()

    def _resolve_create_race(self, draft: ModificationDraft) -> ModificationDraft:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                sql.lock_tenant(connection, draft.tenant_id)
                row = sql.find_identity(connection, draft)
                if row is None:
                    raise ModificationConflict("modification identity conflicts")
                stored = draft_from_row(row)
                if stored.request_hash != draft.request_hash:
                    raise ModificationConflict("idempotency payload differs")
                return stored
        except Error as error:
            raise RepositoryTransactionError(str(error)) from error
        finally:
            connection.close()

    def get(self, tenant_id: str, job_id: str, draft_id: str) -> ModificationDraft:
        connection = self._connection_factory()
        try:
            row = connection.execute(
                "SELECT * FROM modification_drafts WHERE tenant_id=%s AND job_id=%s "
                "AND draft_id=%s",
                (tenant_id, job_id, draft_id),
            ).fetchone()
            if row is None:
                raise ModificationNotFound(draft_id)
            return draft_from_row(row)
        except Error as error:
            raise RepositoryTransactionError(str(error)) from error
        finally:
            connection.close()

    def approve(
        self,
        draft,
        revision,
        quality_baseline,
        quality_job_id,
        queue_payload,
        queue_request_hash,
        stage_run_id,
        *,
        expected_version,
        now,
    ) -> ApprovalReceipt:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                current = sql.locked_draft(connection, draft)
                if current.state is DraftState.APPROVED:
                    if (
                        current.quality_run_id != stage_run_id
                        or current.quality_job_id != quality_job_id
                    ):
                        raise ModificationConflict("draft approved with another run")
                    return ApprovalReceipt(current, stage_run_id, quality_job_id)
                _require_transition(
                    current, {DraftState.PREVIEW_READY}, expected_version
                )
                job = sql.locked_job(connection, draft.job_id)
                sql.require_modifiable(job, revision.parent_revision_id)
                sql.insert_revision(connection, draft.job_id, revision)
                sql.advance_original_job(connection, job)
                sql.create_quality_job(connection, quality_job_id, quality_baseline)
                if self._approval_probe is not None:
                    self._approval_probe()
                sql.insert_queue(
                    connection,
                    draft,
                    quality_job_id,
                    queue_payload,
                    queue_request_hash,
                    stage_run_id,
                    now,
                )
                sql.set_state(
                    connection,
                    current,
                    DraftState.APPROVED,
                    stage_run_id,
                    quality_job_id,
                )
            approved = self.get(draft.tenant_id, draft.job_id, draft.draft_id)
            return ApprovalReceipt(approved, stage_run_id, quality_job_id)
        except UniqueViolation as error:
            raise ModificationConflict("approval identity conflicts") from error
        except Error as error:
            raise RepositoryTransactionError(str(error)) from error
        finally:
            connection.close()

    def discard(
        self, tenant_id, job_id, draft_id, *, expected_version
    ) -> ModificationDraft:
        connection = self._connection_factory()
        try:
            with connection.transaction():
                row = connection.execute(
                    "SELECT * FROM modification_drafts WHERE tenant_id=%s AND "
                    "job_id=%s AND draft_id=%s FOR UPDATE",
                    (tenant_id, job_id, draft_id),
                ).fetchone()
                if row is None:
                    raise ModificationNotFound(draft_id)
                current = draft_from_row(row)
                if current.state is DraftState.DISCARDED:
                    return current
                _require_transition(
                    current,
                    {DraftState.PREVIEW_READY, DraftState.FAILED},
                    expected_version,
                )
                sql.set_state(connection, current, DraftState.DISCARDED, None, None)
            return self.get(tenant_id, job_id, draft_id)
        except Error as error:
            raise RepositoryTransactionError(str(error)) from error
        finally:
            connection.close()


def _require_transition(draft, expected_states, expected_version) -> None:
    if draft.state not in expected_states:
        raise ModificationConflict(f"cannot transition {draft.state.value} draft")
    if draft.version != expected_version:
        raise ModificationStale("draft version is stale")


def _values(draft) -> tuple[object, ...]:
    return (
        draft.draft_id,
        draft.tenant_id,
        draft.job_id,
        draft.idempotency_key,
        draft.request_hash,
        draft.candidate_revision_id,
        draft.state.value,
        draft.version,
        draft.quality_run_id,
        draft.quality_job_id,
        Jsonb(draft_payload(draft)),
    )
