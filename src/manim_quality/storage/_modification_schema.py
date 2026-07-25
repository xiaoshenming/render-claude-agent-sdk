"""SQLite schema for immutable user modification drafts."""

MODIFICATION_SCHEMA = """
CREATE TABLE IF NOT EXISTS modification_drafts (
    draft_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    candidate_revision_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (
        state IN ('PREVIEW_READY', 'FAILED', 'APPROVED', 'DISCARDED')
    ),
    version INTEGER NOT NULL CHECK (version >= 0),
    quality_run_id TEXT UNIQUE,
    quality_job_id TEXT UNIQUE,
    payload TEXT NOT NULL CHECK (json_valid(payload)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (tenant_id, job_id, idempotency_key),
    FOREIGN KEY (job_id) REFERENCES quality_jobs(job_id) ON DELETE RESTRICT,
    FOREIGN KEY (quality_job_id) REFERENCES quality_jobs(job_id) ON DELETE RESTRICT
);

CREATE TRIGGER IF NOT EXISTS reject_modification_identity_update
BEFORE UPDATE ON modification_drafts
WHEN NEW.draft_id IS NOT OLD.draft_id
    OR NEW.tenant_id IS NOT OLD.tenant_id
    OR NEW.job_id IS NOT OLD.job_id
    OR NEW.idempotency_key IS NOT OLD.idempotency_key
    OR NEW.request_hash IS NOT OLD.request_hash
    OR NEW.candidate_revision_id IS NOT OLD.candidate_revision_id
    OR NEW.payload IS NOT OLD.payload
    OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'modification draft content is immutable');
END;
"""
