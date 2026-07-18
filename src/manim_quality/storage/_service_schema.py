"""SQLite schema owned by Task 11 service-delivery infrastructure."""

SERVICE_DELIVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS quality_submissions (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (
        length(request_hash) = 71 AND
        substr(request_hash, 1, 7) = 'sha256:' AND
        substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    stage_run_id TEXT NOT NULL UNIQUE,
    payload BLOB NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE (job_id),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS quality_queue (
    stage_run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    queue_class TEXT NOT NULL CHECK (queue_class IN ('QUALITY', 'CALLBACK', 'HOLD')),
    state TEXT NOT NULL CHECK (
        state IN ('QUEUED', 'RUNNING', 'COMPLETED', 'DEAD_LETTER')
    ),
    payload BLOB NOT NULL,
    request_hash TEXT NOT NULL CHECK (
        length(request_hash) = 71 AND
        substr(request_hash, 1, 7) = 'sha256:' AND
        substr(request_hash, 8) NOT GLOB '*[^0-9a-f]*'
    ),
    attempt INTEGER NOT NULL CHECK (attempt >= 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at TEXT,
    heartbeat_at TEXT,
    deadline TEXT NOT NULL,
    available_at TEXT NOT NULL,
    terminal_reason TEXT,
    callback_url TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (tenant_id, job_id)
        REFERENCES quality_submissions(tenant_id, job_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS quality_queue_claim_idx
ON quality_queue(queue_class, state, available_at, lease_expires_at);

CREATE TRIGGER IF NOT EXISTS reject_quality_queue_identity_update
BEFORE UPDATE ON quality_queue
WHEN NEW.stage_run_id IS NOT OLD.stage_run_id
    OR NEW.tenant_id IS NOT OLD.tenant_id
    OR NEW.job_id IS NOT OLD.job_id
    OR NEW.queue_class IS NOT OLD.queue_class
    OR NEW.payload IS NOT OLD.payload
    OR NEW.request_hash IS NOT OLD.request_hash
    OR NEW.max_attempts IS NOT OLD.max_attempts
    OR NEW.deadline IS NOT OLD.deadline
    OR NEW.callback_url IS NOT OLD.callback_url
    OR NEW.created_at IS NOT OLD.created_at
BEGIN
    SELECT RAISE(ABORT, 'quality queue identity is immutable');
END;

CREATE TABLE IF NOT EXISTS callback_replays (
    event_id TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""
