-- Persisted orchestration transitions, idempotent runs, and durable evidence.

CREATE TABLE quality_state_transitions (
    job_id TEXT NOT NULL REFERENCES quality_jobs(job_id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL CHECK (btrim(run_id) <> ''),
    reason_code TEXT NOT NULL CHECK (btrim(reason_code) <> ''),
    evidence_hash TEXT NOT NULL CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    source_state TEXT NOT NULL,
    target_state TEXT NOT NULL,
    job_version BIGINT NOT NULL CHECK (job_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, run_id)
);

CREATE TABLE quality_runs (
    job_id TEXT NOT NULL REFERENCES quality_jobs(job_id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL CHECK (btrim(run_id) <> ''),
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^sha256:[0-9a-f]{64}$'),
    result_payload JSONB CHECK (
        result_payload IS NULL OR jsonb_typeof(result_payload) = 'object'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, run_id)
);

CREATE TABLE quality_evidence (
    evidence_hash TEXT PRIMARY KEY CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    payload BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE quality_rollbacks (
    job_id TEXT NOT NULL REFERENCES quality_jobs(job_id) ON DELETE RESTRICT,
    run_id TEXT NOT NULL CHECK (btrim(run_id) <> ''),
    rollback_to_revision_id TEXT NOT NULL,
    failed_revision_id TEXT,
    reason_code TEXT NOT NULL CHECK (btrim(reason_code) <> ''),
    evidence_hash TEXT NOT NULL CHECK (evidence_hash ~ '^sha256:[0-9a-f]{64}$'),
    job_version BIGINT NOT NULL CHECK (job_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, run_id),
    FOREIGN KEY (job_id, rollback_to_revision_id)
        REFERENCES quality_revisions(job_id, revision_id) ON DELETE RESTRICT,
    FOREIGN KEY (job_id, failed_revision_id)
        REFERENCES quality_revisions(job_id, revision_id) ON DELETE RESTRICT
);

CREATE TRIGGER reject_quality_state_transition_mutation
BEFORE UPDATE OR DELETE ON quality_state_transitions
FOR EACH ROW EXECUTE FUNCTION reject_quality_revision_mutation();

CREATE TRIGGER reject_quality_evidence_mutation
BEFORE UPDATE OR DELETE ON quality_evidence
FOR EACH ROW EXECUTE FUNCTION reject_quality_revision_mutation();

CREATE TRIGGER reject_quality_rollback_mutation
BEFORE UPDATE OR DELETE ON quality_rollbacks
FOR EACH ROW EXECUTE FUNCTION reject_quality_revision_mutation();
