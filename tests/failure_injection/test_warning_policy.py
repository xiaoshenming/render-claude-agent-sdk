from pathlib import Path

import pytest

from manim_quality.contracts import DeliveryDecision, RevisionStage
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.models import (
    StageAction,
    WarningPolicyDecision,
)
from manim_quality.orchestrator.service import QualityOrchestrator
from manim_quality.storage.database import SQLiteRevisionRepository
from tests.e2e.test_quality_happy_path import (
    VERSIONS,
    FakeAssessment,
    FakeLayoutRecheck,
    FakeLogicVerifier,
    FakeRender,
    FakeRepair,
    FakeSemanticVerifier,
    baseline,
    digest,
    execution_request,
)


class RejectingWarningPolicy:
    def authorize(self, stage, warnings, assessment_hash, request):
        return WarningPolicyDecision(
            stage,
            False,
            tuple(item.evidence_hash for item in warnings),
            VERSIONS.warning_policy_version,
            digest(f"rejected:{stage.value}"),
        )


@pytest.mark.parametrize(
    ("logic_action", "layout_action"),
    [
        (StageAction.WARNING, StageAction.CLEAN),
        (StageAction.CLEAN, StageAction.WARNING),
    ],
)
def test_warning_cannot_certify_without_independent_policy_authorization(
    tmp_path: Path,
    logic_action: StageAction,
    layout_action: StageAction,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    repository.create_job("job-1", baseline())
    service = QualityOrchestrator(
        repository,
        FakeAssessment(logic_action, "logic"),
        FakeRepair(RevisionStage.LOGIC_REPAIR),
        FakeLogicVerifier(),
        FakeAssessment(layout_action, "layout"),
        FakeRepair(RevisionStage.LAYOUT_REPAIR),
        FakeLayoutRecheck(),
        FakeSemanticVerifier(),
        RejectingWarningPolicy(),
        FakeRender(),
        FinalConsistencyGate(),
    )
    try:
        outcome = service.execute(execution_request())
        assert outcome.result.decision is DeliveryDecision.HOLD
        assert outcome.snapshot.delivery_revision_id is None
        assert repository.list_rollbacks("job-1")
    finally:
        repository.close()
