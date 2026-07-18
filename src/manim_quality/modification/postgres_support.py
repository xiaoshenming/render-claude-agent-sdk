"""PostgreSQL statements used by the modification transaction adapter."""

from __future__ import annotations

from datetime import timedelta

from manim_quality.contracts import QualityState
from manim_quality.storage.postgres.revision_codec import revision_parameter

from .codec import draft_from_row
from .errors import ModificationConflict, ModificationNotFound, ModificationStale


def lock_tenant(connection, tenant_id) -> None:
    connection.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (tenant_id,)
    )


def find_identity(connection, draft):
    return connection.execute(
        "SELECT * FROM modification_drafts WHERE draft_id=%s OR "
        "(tenant_id=%s AND job_id=%s AND idempotency_key=%s) FOR UPDATE",
        (draft.draft_id, draft.tenant_id, draft.job_id, draft.idempotency_key),
    ).fetchone()


def locked_draft(connection, draft):
    row = connection.execute(
        "SELECT * FROM modification_drafts WHERE tenant_id=%s AND job_id=%s "
        "AND draft_id=%s FOR UPDATE",
        (draft.tenant_id, draft.job_id, draft.draft_id),
    ).fetchone()
    if row is None:
        raise ModificationNotFound(draft.draft_id)
    return draft_from_row(row)


def locked_job(connection, job_id):
    row = connection.execute(
        "SELECT * FROM quality_jobs WHERE job_id=%s FOR UPDATE", (job_id,)
    ).fetchone()
    if row is None:
        raise ModificationNotFound(job_id)
    return row


def require_modifiable(job, parent_revision_id) -> None:
    state = QualityState(job["state"])
    if state not in {QualityState.ACCEPTED, QualityState.ACCEPTED_WITH_WARNING}:
        raise ModificationConflict("only accepted jobs may be modified")
    parent = job["delivery_revision_id"] or job["render_baseline_revision_id"]
    if parent_revision_id != parent:
        raise ModificationConflict("draft parent is no longer current")


def insert_revision(connection, job_id, revision) -> None:
    connection.execute(
        "INSERT INTO quality_revisions (revision_id,job_id,parent_revision_id,"
        "stage,payload,code_hash,semantic_fingerprint,render_manifest_hash) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            revision.revision_id,
            job_id,
            revision.parent_revision_id,
            revision.stage.value,
            revision_parameter(revision),
            revision.code_hash,
            revision.semantic_fingerprint,
            revision.render_manifest_hash,
        ),
    )


def advance_original_job(connection, job) -> None:
    cursor = connection.execute(
        "UPDATE quality_jobs SET version=version+1 WHERE job_id=%s AND version=%s",
        (job["job_id"], job["version"]),
    )
    if cursor.rowcount != 1:
        raise ModificationStale("quality job changed during approval")


def create_quality_job(connection, job_id, baseline) -> None:
    connection.execute(
        "INSERT INTO quality_jobs (job_id,version,state,"
        "render_baseline_revision_id,render_baseline_evidence_hash) "
        "VALUES (%s,0,%s,%s,%s)",
        (
            job_id,
            QualityState.BASELINE_READY.value,
            baseline.revision_id,
            baseline.render_manifest_hash,
        ),
    )
    insert_revision(connection, job_id, baseline)
    connection.execute(
        "INSERT INTO quality_checkpoint_history (job_id,checkpoint,revision_id,"
        "evidence_hash,job_version) VALUES (%s,%s,%s,%s,0)",
        (
            job_id,
            "render_baseline_revision_id",
            baseline.revision_id,
            baseline.render_manifest_hash,
        ),
    )


def insert_queue(
    connection, draft, quality_job_id, payload, request_hash, run_id, now
) -> None:
    callback = connection.execute(
        "SELECT q.callback_url FROM quality_submissions s JOIN quality_queue q "
        "ON q.stage_run_id=s.stage_run_id WHERE s.tenant_id=%s AND s.job_id=%s",
        (draft.tenant_id, draft.job_id),
    ).fetchone()
    if callback is None:
        raise ModificationConflict("quality submission is missing")
    connection.execute(
        "INSERT INTO quality_submissions (tenant_id,job_id,idempotency_key,"
        "request_hash,stage_run_id,payload,created_at) VALUES "
        "(%s,%s,%s,%s,%s,%s,%s)",
        (
            draft.tenant_id,
            quality_job_id,
            f"modification:{draft.draft_id}",
            request_hash,
            run_id,
            payload,
            now,
        ),
    )
    connection.execute(
        "INSERT INTO quality_queue (stage_run_id,tenant_id,job_id,queue_class,"
        "state,payload,request_hash,attempt,max_attempts,available_at,deadline,"
        "callback_url) VALUES (%s,%s,%s,'QUALITY','QUEUED',%s,%s,0,3,%s,%s,%s)",
        (
            run_id,
            draft.tenant_id,
            quality_job_id,
            payload,
            request_hash,
            now,
            now + timedelta(hours=2),
            callback["callback_url"],
        ),
    )


def set_state(connection, draft, state, run_id, quality_job_id) -> None:
    cursor = connection.execute(
        "UPDATE modification_drafts SET state=%s,version=version+1,"
        "quality_run_id=%s,quality_job_id=%s,updated_at=now() "
        "WHERE draft_id=%s AND version=%s",
        (state.value, run_id, quality_job_id, draft.draft_id, draft.version),
    )
    if cursor.rowcount != 1:
        raise ModificationStale("draft changed concurrently")
