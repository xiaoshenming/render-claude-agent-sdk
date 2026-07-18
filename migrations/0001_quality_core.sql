-- PostgreSQL production schema. The SQLite adapter is for local development and tests only.

CREATE TABLE quality_jobs (
    job_id TEXT PRIMARY KEY CHECK (btrim(job_id) <> ''),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    state TEXT NOT NULL CHECK (
        state IN (
            'RECEIVED', 'INPUT_VALIDATED', 'BASELINE_READY',
            'LOGIC_REVIEWING', 'POLICY_EVALUATING', 'LOGIC_REPAIRING',
            'LOGIC_VERIFYING', 'LOGIC_CERTIFIED',
            'LOGIC_CERTIFIED_WITH_WARNING', 'LAYOUT_CHECKING',
            'LAYOUT_REPAIRING', 'LAYOUT_VERIFYING', 'LAYOUT_CERTIFIED',
            'LAYOUT_CERTIFIED_WITH_WARNING', 'FINAL_CONSISTENCY_GATE',
            'ACCEPTED', 'ACCEPTED_WITH_WARNING', 'REGENERATE', 'HOLD', 'FAILED'
        )
    ),
    render_baseline_revision_id TEXT NOT NULL,
    logic_certified_revision_id TEXT,
    layout_certified_revision_id TEXT,
    delivery_revision_id TEXT,
    render_baseline_evidence_hash TEXT CHECK (
        render_baseline_evidence_hash IS NULL OR
        render_baseline_evidence_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    logic_certified_evidence_hash TEXT CHECK (
        logic_certified_evidence_hash IS NULL OR
        logic_certified_evidence_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    layout_certified_evidence_hash TEXT CHECK (
        layout_certified_evidence_hash IS NULL OR
        layout_certified_evidence_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    delivery_evidence_hash TEXT CHECK (
        delivery_evidence_hash IS NULL OR
        delivery_evidence_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE quality_revisions (
    revision_id TEXT PRIMARY KEY CHECK (btrim(revision_id) <> ''),
    job_id TEXT NOT NULL,
    parent_revision_id TEXT,
    stage TEXT NOT NULL CHECK (
        stage IN (
            'BASELINE', 'RENDER_REPAIR', 'LOGIC_REPAIR',
            'LAYOUT_REPAIR', 'USER_MODIFICATION'
        )
    ),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    code_hash TEXT NOT NULL CHECK (code_hash ~ '^sha256:[0-9a-f]{64}$'),
    semantic_fingerprint TEXT NOT NULL CHECK (
        semantic_fingerprint ~ '^sha256:[0-9a-f]{64}$'
    ),
    render_manifest_hash TEXT CHECK (
        render_manifest_hash IS NULL OR
        render_manifest_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT quality_revision_job_revision_unique UNIQUE (job_id, revision_id),
    CONSTRAINT quality_revision_job_fk FOREIGN KEY (job_id)
        REFERENCES quality_jobs(job_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT quality_revision_parent_fk
        FOREIGN KEY (job_id, parent_revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT quality_revision_root_check CHECK (
        (parent_revision_id IS NULL AND stage = 'BASELINE') OR
        (parent_revision_id IS NOT NULL AND stage <> 'BASELINE')
    )
);

CREATE UNIQUE INDEX quality_revision_one_root_per_job
    ON quality_revisions(job_id)
    WHERE parent_revision_id IS NULL;

ALTER TABLE quality_jobs
    ADD CONSTRAINT quality_job_render_baseline_fk
    FOREIGN KEY (job_id, render_baseline_revision_id)
    REFERENCES quality_revisions(job_id, revision_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE quality_checkpoint_history (
    job_id TEXT NOT NULL,
    checkpoint TEXT NOT NULL CHECK (
        checkpoint IN (
            'RENDER_BASELINE', 'LOGIC_CERTIFIED',
            'LAYOUT_CERTIFIED', 'DELIVERY'
        )
    ),
    revision_id TEXT NOT NULL,
    evidence_hash TEXT NOT NULL CHECK (
        evidence_hash ~ '^sha256:[0-9a-f]{64}$'
    ),
    job_version BIGINT NOT NULL CHECK (job_version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (job_id, checkpoint, job_version),
    CONSTRAINT quality_checkpoint_revision_fk
        FOREIGN KEY (job_id, revision_id)
        REFERENCES quality_revisions(job_id, revision_id)
        ON DELETE RESTRICT
);

CREATE FUNCTION reject_quality_revision_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'quality revision and checkpoint history are immutable';
END;
$$;

CREATE TRIGGER reject_quality_revision_mutation
BEFORE UPDATE OR DELETE ON quality_revisions
FOR EACH ROW EXECUTE FUNCTION reject_quality_revision_mutation();

CREATE TRIGGER reject_quality_checkpoint_history_mutation
BEFORE UPDATE OR DELETE ON quality_checkpoint_history
FOR EACH ROW EXECUTE FUNCTION reject_quality_revision_mutation();

ALTER TABLE quality_jobs
    ADD CONSTRAINT quality_job_logic_certified_fk
    FOREIGN KEY (job_id, logic_certified_revision_id)
    REFERENCES quality_revisions(job_id, revision_id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE quality_jobs
    ADD CONSTRAINT quality_job_layout_certified_fk
    FOREIGN KEY (job_id, layout_certified_revision_id)
    REFERENCES quality_revisions(job_id, revision_id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE quality_jobs
    ADD CONSTRAINT quality_job_delivery_fk
    FOREIGN KEY (job_id, delivery_revision_id)
    REFERENCES quality_revisions(job_id, revision_id)
    DEFERRABLE INITIALLY DEFERRED;
