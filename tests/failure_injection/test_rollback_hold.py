from pathlib import Path

import pytest

from manim_quality.contracts import DeliveryDecision, RevisionStage
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.models import StageAction
from manim_quality.orchestrator.service import QualityOrchestrator
from manim_quality.revisions.store import RepositoryTransactionError
from manim_quality.storage.database import SQLiteRevisionRepository
from tests.e2e.test_quality_happy_path import (
    FakeAssessment,
    FakeLayoutRecheck,
    FakeLogicVerifier,
    FakeRender,
    FakeRepair,
    FakeSemanticVerifier,
    FakeWarningPolicy,
    baseline,
    execution_request,
)


class FailingLogicVerifier(FakeLogicVerifier):
    def verify(self, candidate, render, assessment, request, warning_policy):
        raise RuntimeError("independent verifier rejected candidate")


def test_failure_after_candidate_append_records_explicit_rollback(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    repository.create_job("job-1", baseline())
    service = QualityOrchestrator(
        repository,
        FakeAssessment(StageAction.REPAIR, "logic"),
        FakeRepair(RevisionStage.LOGIC_REPAIR),
        FailingLogicVerifier(),
        FakeAssessment(StageAction.CLEAN, "layout"),
        FakeRepair(RevisionStage.LAYOUT_REPAIR),
        FakeLayoutRecheck(),
        FakeSemanticVerifier(),
        FakeWarningPolicy(),
        FakeRender(),
        FinalConsistencyGate(),
    )
    request = execution_request()

    try:
        outcome = service.execute(request)
        rollback = repository.list_rollbacks("job-1")[-1]

        assert outcome.result.decision is DeliveryDecision.HOLD
        assert repository.get_revision("logic-fixed").revision_id == "logic-fixed"
        assert outcome.snapshot.logic_certified_revision_id is None
        assert rollback.rollback_to_revision_id == "baseline"
        assert rollback.failed_revision_id == "logic-fixed"
        assert (
            repository.get_run_result(
                request.job_id, request.run_id, request.request_hash
            )
            == outcome.result
        )
    finally:
        repository.close()


def test_hold_transition_rollback_evidence_and_result_are_atomic(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "atomic-hold.sqlite3")
    repository.create_job("job-1", baseline())
    repository._connection.execute(  # type: ignore[attr-defined]
        """
        CREATE TRIGGER inject_hold_failure
        BEFORE UPDATE ON quality_jobs
        WHEN NEW.state = 'HOLD'
        BEGIN
            SELECT RAISE(ABORT, 'injected hold failure');
        END
        """
    )
    request = execution_request()
    runner = QualityOrchestrator(
        repository,
        FakeAssessment(StageAction.REPAIR, "logic"),
        FakeRepair(RevisionStage.LOGIC_REPAIR),
        FailingLogicVerifier(),
        FakeAssessment(StageAction.CLEAN, "layout"),
        FakeRepair(RevisionStage.LAYOUT_REPAIR),
        FakeLayoutRecheck(),
        FakeSemanticVerifier(),
        FakeWarningPolicy(),
        FakeRender(),
        FinalConsistencyGate(),
    )
    try:
        with pytest.raises(RepositoryTransactionError, match="injected hold failure"):
            runner.execute(request)
        evidence = repository._connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*) FROM quality_evidence"
        ).fetchone()[0]
        assert evidence == 0
        assert repository.list_rollbacks("job-1") == ()
        assert (
            repository.get_run_result(
                request.job_id, request.run_id, request.request_hash
            )
            is None
        )
        assert repository.get_job("job-1").state.value == "LOGIC_VERIFYING"
    finally:
        repository.close()
