"""SQLite statements used by the modification approval transaction."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from manim_quality.contracts import QualityState
from manim_quality.storage._revision_records import revision_values

from .errors import ModificationConflict


def create_quality_job(connection, job_id, baseline) -> None:
    connection.execute(
        "INSERT INTO quality_jobs (job_id,version,state,"
        "render_baseline_revision_id,render_baseline_evidence_hash) "
        "VALUES (?,0,?,?,?)",
        (
            job_id,
            QualityState.BASELINE_READY.value,
            baseline.revision_id,
            baseline.render_manifest_hash,
        ),
    )
    connection.execute(
        "INSERT INTO quality_revisions (revision_id,job_id,parent_revision_id,"
        "stage,payload,code_hash,semantic_fingerprint,render_manifest_hash) "
        "VALUES (?,?,?,?,?,?,?,?)",
        revision_values(job_id, baseline),
    )
    connection.execute(
        "INSERT INTO quality_checkpoint_history (job_id,checkpoint,revision_id,"
        "evidence_hash,job_version) VALUES (?,?,?,?,0)",
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
        "ON q.stage_run_id=s.stage_run_id WHERE s.tenant_id=? AND s.job_id=?",
        (draft.tenant_id, draft.job_id),
    ).fetchone()
    if callback is None:
        raise ModificationConflict("quality submission is missing")
    deadline = now + timedelta(hours=2)
    connection.execute(
        "INSERT INTO quality_submissions (tenant_id,job_id,idempotency_key,"
        "request_hash,stage_run_id,payload,created_at) VALUES (?,?,?,?,?,?,?)",
        (
            draft.tenant_id,
            quality_job_id,
            f"modification:{draft.draft_id}",
            request_hash,
            run_id,
            payload,
            _iso(now),
        ),
    )
    connection.execute(
        "INSERT INTO quality_queue (stage_run_id, tenant_id, job_id, "
        "queue_class, state, payload, request_hash, attempt, max_attempts, "
        "available_at, deadline, callback_url) VALUES (?, ?, ?, 'QUALITY', "
        "'QUEUED', ?, ?, 0, 3, ?, ?, ?)",
        (
            run_id,
            draft.tenant_id,
            quality_job_id,
            payload,
            request_hash,
            _iso(now),
            _iso(deadline),
            callback["callback_url"],
        ),
    )


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()
