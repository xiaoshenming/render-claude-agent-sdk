from dataclasses import replace
from pathlib import Path

import pytest

from manim_quality.contracts import DeliveryDecision, RevisionStage
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.certificates import SemanticPreservationCertificate
from manim_quality.orchestrator.identity import ComponentIdentity, ComponentRole
from manim_quality.orchestrator.models import SemanticDecision, StageAction
from manim_quality.orchestrator.service import QualityOrchestrator
from manim_quality.storage.database import SQLiteRevisionRepository
from tests.e2e.test_quality_happy_path import (
    FakeAssessment,
    FakeLayoutRecheck,
    FakeLogicVerifier,
    FakeRender,
    FakeRepair,
    FakeWarningPolicy,
    baseline,
    digest,
    execution_request,
)


class RejectingSemanticVerifier:
    identity = ComponentIdentity(
        ComponentRole.LAYOUT_SEMANTIC_VERIFY,
        "rejecting-layout-semantic-verify",
        digest("profile:rejecting-layout-semantic-verify"),
        "session:rejecting-layout-semantic-verify",
    )

    def verify(self, logic_checkpoint, final, render, assessment, request):
        return SemanticPreservationCertificate(
            request.job_id,
            logic_checkpoint.revision_id,
            logic_checkpoint.code_hash,
            final.revision_id,
            final.code_hash,
            request.request_hash,
            request.question_hash,
            request.plan_hash,
            self.identity,
            request.versions.layout_semantic_verifier_version,
            digest("semantic-verifier:rejected"),
            SemanticDecision.REJECTED,
        )


def test_layout_geometry_change_rejected_by_independent_semantic_verifier(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    repository.create_job("job-1", baseline())
    runner = QualityOrchestrator(
        repository,
        FakeAssessment(StageAction.CLEAN, "logic"),
        FakeRepair(RevisionStage.LOGIC_REPAIR),
        FakeLogicVerifier(),
        FakeAssessment(StageAction.REPAIR, "layout"),
        FakeRepair(RevisionStage.LAYOUT_REPAIR),
        FakeLayoutRecheck(),
        RejectingSemanticVerifier(),
        FakeWarningPolicy(),
        FakeRender(),
        FinalConsistencyGate(),
    )
    try:
        outcome = runner.execute(execution_request())
        assert outcome.result.decision is DeliveryDecision.HOLD
        assert repository.get_revision("layout-fixed").revision_id == "layout-fixed"
        assert outcome.snapshot.layout_certified_revision_id is None
        assert repository.list_rollbacks("job-1")[-1].failed_revision_id == (
            "layout-fixed"
        )
    finally:
        repository.close()


def valid_semantic_certificate() -> SemanticPreservationCertificate:
    return SemanticPreservationCertificate(
        "job-1",
        "logic-revision",
        digest("logic-code"),
        "final-revision",
        digest("final-code"),
        digest("request"),
        digest("question"),
        digest("plan"),
        RejectingSemanticVerifier.identity,
        "semantic-verifier-v1",
        digest("semantic-evidence"),
        SemanticDecision.PRESERVED,
    )


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "error_type"),
    [
        ("job_id", "", ValueError),
        ("logic_revision_id", "", ValueError),
        ("final_revision_id", "", ValueError),
        ("logic_code_hash", "sha256:" + "A" * 64, ValueError),
        ("final_code_hash", "sha256:" + "z" * 64, ValueError),
        ("request_hash", "not-a-hash", ValueError),
        ("question_hash", "not-a-hash", ValueError),
        ("plan_hash", "not-a-hash", ValueError),
        ("evidence_hash", "sha256:" + "g" * 64, ValueError),
        (
            "verifier_identity",
            ComponentIdentity(
                ComponentRole.LOGIC_VERIFY,
                "wrong-role",
                digest("wrong-role-profile"),
                "wrong-role-session",
            ),
            ValueError,
        ),
        ("verifier_version", "", ValueError),
        ("decision", "PRESERVED", TypeError),
    ],
)
def test_semantic_certificate_rejects_malformed_authority(
    field_name: str, invalid_value: object, error_type: type[Exception]
) -> None:
    with pytest.raises(error_type):
        replace(valid_semantic_certificate(), **{field_name: invalid_value})
