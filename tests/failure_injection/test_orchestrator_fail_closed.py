from dataclasses import replace
from pathlib import Path

import pytest

from manim_quality.contracts import DeliveryDecision, RevisionStage
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.failures import HoldPersistenceError
from manim_quality.orchestrator.models import StageAction
from manim_quality.orchestrator.revision_models import CandidateRevision
from manim_quality.orchestrator.service import QualityOrchestrator
from manim_quality.revisions.store import (
    DuplicateRunConflict,
    RepositoryTransactionError,
    StaleWrite,
    TransitionReplayAdvanced,
)
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
    digest,
    execution_request,
    service,
)


def configured_service(repository, logic_review, logic_verify=None, renderer=None):
    return QualityOrchestrator(
        repository,
        logic_review,
        FakeRepair(RevisionStage.LOGIC_REPAIR),
        logic_verify or FakeLogicVerifier(),
        FakeAssessment(StageAction.CLEAN, "layout"),
        FakeRepair(RevisionStage.LAYOUT_REPAIR),
        FakeLayoutRecheck(),
        FakeSemanticVerifier(),
        FakeWarningPolicy(),
        renderer or FakeRender(),
        FinalConsistencyGate(),
    )


def test_repository_transaction_failure_is_not_converted_to_business_hold(
    tmp_path: Path,
) -> None:
    class FailingRepository(SQLiteRevisionRepository):
        def transition_state(self, *args, **kwargs):
            raise RepositoryTransactionError("database unavailable")

    repository = FailingRepository(tmp_path / "repository-failure.sqlite3")
    repository.create_job("job-1", baseline())
    request = execution_request()
    try:
        with pytest.raises(RepositoryTransactionError, match="database unavailable"):
            configured_service(
                repository, FakeAssessment(StageAction.CLEAN, "logic")
            ).execute(request)
        assert (
            repository.get_run_result(
                request.job_id, request.run_id, request.request_hash
            )
            is None
        )
        assert repository.list_rollbacks(request.job_id) == ()
    finally:
        repository.close()


def test_malformed_logic_certificate_never_promotes_checkpoint(tmp_path: Path) -> None:
    class MismatchedVerifier(FakeLogicVerifier):
        def verify(self, candidate, render, assessment, request, warning_policy):
            certificate = super().verify(
                candidate, render, assessment, request, warning_policy
            )
            return replace(certificate, code_hash=digest("unrelated-code"))

    repository = SQLiteRevisionRepository(tmp_path / "malformed.sqlite3")
    repository.create_job("job-1", baseline())
    try:
        outcome = configured_service(
            repository,
            FakeAssessment(StageAction.CLEAN, "logic"),
            MismatchedVerifier(),
        ).execute(execution_request())
        assert outcome.result.decision is DeliveryDecision.HOLD
        assert outcome.snapshot.logic_certified_revision_id is None
    finally:
        repository.close()


def test_render_error_is_held_and_persisted_as_render_failure(tmp_path: Path) -> None:
    class FailingRender(FakeRender):
        def render(self, candidate, request):
            raise RuntimeError("renderer unavailable")

    repository = SQLiteRevisionRepository(tmp_path / "render-error.sqlite3")
    repository.create_job("job-1", baseline())
    request = execution_request()
    try:
        outcome = configured_service(
            repository,
            FakeAssessment(StageAction.REPAIR, "logic"),
            renderer=FailingRender(),
        ).execute(request)
        assert outcome.result.decision is DeliveryDecision.HOLD
        assert outcome.result.warnings == ("render_error:renderer unavailable",)
        assert outcome.snapshot.logic_certified_revision_id is None
        assert (
            repository.get_run_result(
                request.job_id, request.run_id, request.request_hash
            )
            == outcome.result
        )
    finally:
        repository.close()


def test_stale_worker_cannot_hold_or_mutate_newer_state(tmp_path: Path) -> None:
    database = tmp_path / "stale.sqlite3"
    repository = SQLiteRevisionRepository(database)
    competing = SQLiteRevisionRepository(database)
    repository.create_job("job-1", baseline())
    request = execution_request()
    newer = []
    transitions_before_stale = []

    class RacingReview(FakeAssessment):
        def assess(self, revision, execution):
            snapshot = competing.get_job("job-1")
            proposal = FakeRepair(RevisionStage.LOGIC_REPAIR).propose(
                revision,
                super().assess(revision, execution),
                execution,
            )
            bound = CandidateRevision.from_proposal(proposal).materialize(
                digest("manifest:competing")
            )
            newer.append(
                competing.append_revision(
                    "job-1", bound.revision, expected_version=snapshot.version
                )
            )
            transitions_before_stale.append(competing.list_transitions("job-1"))
            return super().assess(revision, execution)

    try:
        runner = configured_service(
            repository, RacingReview(StageAction.CLEAN, "logic")
        )
        with pytest.raises(StaleWrite):
            runner.execute(request)
        assert repository.get_job("job-1") == newer[0]
        assert repository.list_transitions("job-1") == transitions_before_stale[0]
        assert repository.list_rollbacks("job-1") == ()
        assert repository.get_run_result("job-1", "run-1", request.request_hash) is None
    finally:
        competing.close()
        repository.close()


def test_advanced_transition_replay_does_not_enter_hold(tmp_path: Path) -> None:
    class ReplayAdvancedRepository(SQLiteRevisionRepository):
        def transition_state(self, *args, **kwargs):
            raise TransitionReplayAdvanced("newer transition already persisted")

    repository = ReplayAdvancedRepository(tmp_path / "replay-advanced.sqlite3")
    repository.create_job("job-1", baseline())
    request = execution_request()
    before = repository.get_job("job-1")
    try:
        with pytest.raises(TransitionReplayAdvanced):
            configured_service(
                repository, FakeAssessment(StageAction.CLEAN, "logic")
            ).execute(request)
        assert repository.get_job("job-1") == before
        assert repository.list_rollbacks("job-1") == ()
        assert repository.get_run_result("job-1", "run-1", request.request_hash) is None
    finally:
        repository.close()


def test_hold_contention_exhaustion_never_returns_unpersisted_hold(
    tmp_path: Path,
) -> None:
    class AlwaysStaleHoldRepository(SQLiteRevisionRepository):
        hold_attempts = 0

        def finalize_hold(self, *args, **kwargs):
            self.hold_attempts += 1
            expected = kwargs["expected_version"]
            raise StaleWrite("job-1", expected, expected + 1)

    class FailingReview:
        def assess(self, revision, request):
            raise RuntimeError("checker unavailable")

    repository = AlwaysStaleHoldRepository(tmp_path / "hold-contention.sqlite3")
    repository.create_job("job-1", baseline())
    request = execution_request()
    try:
        with pytest.raises(HoldPersistenceError, match="job-1.*run-1"):
            configured_service(repository, FailingReview()).execute(request)
        assert repository.hold_attempts == 2
        assert repository.get_run_result("job-1", "run-1", request.request_hash) is None
    finally:
        repository.close()


@pytest.mark.parametrize(
    "failure", [TimeoutError("sdk timeout"), RuntimeError("checker error")]
)
def test_stage_failure_holds_last_checkpoint(
    tmp_path: Path, failure: Exception
) -> None:
    class FailingReview:
        def assess(self, revision, request):
            raise failure

    repository = SQLiteRevisionRepository(tmp_path / "failure.sqlite3")
    repository.create_job("job-1", baseline())
    try:
        outcome = configured_service(repository, FailingReview()).execute(
            execution_request()
        )
        assert outcome.result.decision is DeliveryDecision.HOLD
        assert outcome.snapshot.logic_certified_revision_id is None
        assert repository.list_rollbacks("job-1")[-1].rollback_to_revision_id == (
            "baseline"
        )
    finally:
        repository.close()


def test_duplicate_run_is_idempotent_and_conflicting_payload_fails(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    repository.create_job("job-1", baseline())
    request = execution_request()
    try:
        runner = service(repository, StageAction.CLEAN, StageAction.CLEAN)
        first = runner.execute(request)
        assert runner.execute(request).result == first.result
        with pytest.raises(DuplicateRunConflict):
            runner.execute(replace(request, request_hash="sha256:" + "f" * 64))
    finally:
        repository.close()
