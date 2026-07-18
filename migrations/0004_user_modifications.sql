CREATE TABLE modification_drafts (
    draft_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    job_id TEXT NOT NULL REFERENCES quality_jobs(job_id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    candidate_revision_id TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (
        state IN ('PREVIEW_READY', 'FAILED', 'APPROVED', 'DISCARDED')
    ),
    version INTEGER NOT NULL CHECK (version >= 0),
    quality_run_id TEXT UNIQUE,
    quality_job_id TEXT UNIQUE REFERENCES quality_jobs(job_id) ON DELETE RESTRICT,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, job_id, idempotency_key)
);

CREATE FUNCTION reject_modification_identity_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(
        NEW.draft_id, NEW.tenant_id, NEW.job_id, NEW.idempotency_key,
        NEW.request_hash, NEW.candidate_revision_id, NEW.payload, NEW.created_at
    ) IS DISTINCT FROM ROW(
        OLD.draft_id, OLD.tenant_id, OLD.job_id, OLD.idempotency_key,
        OLD.request_hash, OLD.candidate_revision_id, OLD.payload, OLD.created_at
    ) THEN
        RAISE EXCEPTION 'modification draft content is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER reject_modification_identity_update
BEFORE UPDATE ON modification_drafts
FOR EACH ROW EXECUTE FUNCTION reject_modification_identity_update();

CREATE INDEX modification_drafts_lookup_idx
ON modification_drafts(tenant_id, job_id, draft_id);
