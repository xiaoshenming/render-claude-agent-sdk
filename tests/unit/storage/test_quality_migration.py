from pathlib import Path


def test_postgres_migration_contains_only_quality_revision_core() -> None:
    migration = Path("migrations/0001_quality_core.sql").read_text(encoding="utf-8")
    lowered = migration.lower()

    assert "create table quality_jobs" in lowered
    assert "create table quality_revisions" in lowered
    assert "create table quality_checkpoint_history" in lowered
    assert "payload jsonb" in lowered
    assert "created_at" in lowered
    assert "unique" in lowered
    assert "foreign key" in lowered
    assert "check" in lowered
    for checkpoint in (
        "render_baseline_revision_id",
        "logic_certified_revision_id",
        "layout_certified_revision_id",
        "delivery_revision_id",
    ):
        assert checkpoint in lowered
    assert "sqlite adapter" in lowered
    assert "reject_quality_revision_mutation" in lowered
    assert "queue" not in lowered
    assert "api_request" not in lowered


def test_orchestration_migration_has_state_runs_and_evidence_without_queue() -> None:
    migration = Path("migrations/0002_orchestration_state.sql").read_text(
        encoding="utf-8"
    )
    lowered = migration.lower()

    assert "create table quality_state_transitions" in lowered
    assert "create table quality_runs" in lowered
    assert "create table quality_evidence" in lowered
    assert "create table quality_rollbacks" in lowered
    assert "primary key (job_id, run_id)" in lowered
    assert "reject_quality_state_transition_mutation" in lowered
    assert "reject_quality_evidence_mutation" in lowered
    assert "reject_quality_rollback_mutation" in lowered
    for excluded in ("queue", "lease", "heartbeat", "outbox"):
        assert excluded not in lowered
