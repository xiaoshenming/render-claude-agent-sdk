CREATE TABLE quality_submissions (
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (
        request_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    stage_run_id TEXT NOT NULL UNIQUE,
    payload BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, job_id),
    UNIQUE (job_id),
    UNIQUE (tenant_id, idempotency_key)
);

CREATE TABLE quality_queue (
    stage_run_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    queue_class TEXT NOT NULL CHECK (
        queue_class IN ('QUALITY', 'CALLBACK', 'HOLD')
    ),
    state TEXT NOT NULL CHECK (
        state IN ('QUEUED', 'RUNNING', 'COMPLETED', 'DEAD_LETTER')
    ),
    payload BYTEA NOT NULL,
    request_hash TEXT NOT NULL CHECK (
        request_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    attempt INTEGER NOT NULL CHECK (attempt >= 0),
    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
    lease_owner TEXT,
    lease_token TEXT,
    lease_expires_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    deadline TIMESTAMPTZ NOT NULL,
    available_at TIMESTAMPTZ NOT NULL,
    terminal_reason TEXT,
    callback_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (tenant_id, job_id)
        REFERENCES quality_submissions(tenant_id, job_id) ON DELETE RESTRICT
);

CREATE INDEX quality_queue_claim_idx
    ON quality_queue(queue_class, state, available_at, lease_expires_at);

CREATE FUNCTION reject_quality_queue_identity_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(
        NEW.stage_run_id, NEW.tenant_id, NEW.job_id, NEW.queue_class,
        NEW.payload, NEW.request_hash, NEW.max_attempts, NEW.deadline,
        NEW.callback_url, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.stage_run_id, OLD.tenant_id, OLD.job_id, OLD.queue_class,
        OLD.payload, OLD.request_hash, OLD.max_attempts, OLD.deadline,
        OLD.callback_url, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'quality queue identity is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER reject_quality_queue_identity_update
BEFORE UPDATE ON quality_queue
FOR EACH ROW EXECUTE FUNCTION reject_quality_queue_identity_update();

CREATE TABLE callback_replays (
    event_id TEXT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX callback_replays_expiry_idx ON callback_replays(expires_at);
