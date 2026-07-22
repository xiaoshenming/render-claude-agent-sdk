from pathlib import Path

import pytest

from manim_quality.contracts import (
    DeliveryDecision,
    PatchScope,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.certificates import (
    LayoutCertificate,
    LogicCertificate,
    SemanticPreservationCertificate,
)
from manim_quality.orchestrator.identity import ComponentIdentity, ComponentRole
from manim_quality.orchestrator.models import (
    AgentIdentity,
    ExecutionRequest,
    RenderBinding,
    RenderedCandidate,
    SemanticDecision,
    StageAction,
    StageAssessment,
    VersionBindings,
    WarningPolicyDecision,
    WarningRecord,
)
from manim_quality.orchestrator.revision_models import (
    BoundRevision,
    RepairProposal,
)
from manim_quality.orchestrator.service import QualityOrchestrator
from manim_quality.revisions import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_text,
)
from manim_quality.storage.database import SQLiteRevisionRepository
from .quality_happy_path_fakes import FakeRepair, FakeRender, digest

SOURCE = """\
class Lesson(Scene):
    def construct(self):
        item = Dot()
        item.shift(RIGHT)
        self.add(item)
"""


AGENT = AgentIdentity("model-v1", "prompt-v1", "tools-v1")
VERSIONS = VersionBindings(
    "config-v1",
    "schema-v1",
    "renderer-v1",
    "environment-v1",
    AGENT,
    AGENT,
    AGENT,
    "logic-validator-v1",
    "layout-detector-v1",
    "layout-policy-v1",
    AGENT,
    "layout-recheck-v1",
    "layout-semantic-v1",
    "warning-policy-v1",
    "gate-v1",
)


def baseline() -> Revision:
    return Revision(
        "baseline",
        None,
        RevisionStage.BASELINE,
        code_hash(SOURCE),
        semantic_fingerprint(SOURCE),
        scene_fingerprints(SOURCE),
        digest("manifest:baseline"),
        (),
        PatchScope.FULL_CANDIDATE,
        RevisionCreator.SYSTEM,
        0,
    )


def execution_request() -> ExecutionRequest:
    return ExecutionRequest(
        "job-1",
        "run-1",
        digest("request:1"),
        digest("question"),
        digest("plan"),
        SOURCE,
        "artifact://code/original",
        "artifact://render/original",
        digest("render-config"),
        digest("assets"),
        digest("dependencies"),
        ("Lesson",),
        digest("environment-evidence"),
        VERSIONS,
    )


class FakeAssessment:
    def __init__(self, action: StageAction, label: str) -> None:
        self.action = action
        self.label = label

    def assess(self, revision, request) -> StageAssessment:
        warnings = ()
        if self.action is StageAction.WARNING:
            warnings = (
                WarningRecord(
                    f"{self.label}.low_risk",
                    "Low-risk observation",
                    digest(f"warning:{self.label}"),
                ),
            )
        return StageAssessment(
            self.action, digest(f"assessment:{self.label}"), warnings
        )


class FakeLogicVerifier:
    identity = ComponentIdentity(
        ComponentRole.LOGIC_VERIFY,
        "fake-logic-verify",
        digest("profile:logic-verify"),
        "session:logic-verify",
    )

    def verify(self, candidate, render, assessment, request, warning_policy):
        return LogicCertificate(
            request.job_id,
            candidate.revision_id,
            candidate.code_hash,
            candidate.semantic_fingerprint,
            candidate.layout_invariant_fingerprint,
            request.request_hash,
            request.question_hash,
            request.plan_hash,
            request.code_ref,
            request.render_manifest_ref,
            assessment.evidence_hash,
            render.render_manifest_hash,
            render.manifest_evidence_hash,
            request.versions,
            assessment.warnings,
            None if warning_policy is None else warning_policy.evidence_hash,
        )


class FakeLayoutRecheck:
    identity = ComponentIdentity(
        ComponentRole.LAYOUT_RECHECK,
        "fake-layout-recheck",
        digest("profile:layout-recheck"),
        "session:layout-recheck",
    )

    def verify(
        self, candidate, render, assessment, logic_checkpoint, request, warning_policy
    ):
        return LayoutCertificate(
            request.job_id,
            candidate.revision_id,
            candidate.code_hash,
            render.render_manifest_hash,
            logic_checkpoint.revision_id,
            request.request_hash,
            assessment.evidence_hash,
            render.manifest_evidence_hash,
            0,
            request.versions,
            assessment.warnings,
            None if warning_policy is None else warning_policy.evidence_hash,
        )


class FakeSemanticVerifier:
    identity = ComponentIdentity(
        ComponentRole.LAYOUT_SEMANTIC_VERIFY,
        "fake-layout-semantic-verify",
        digest("profile:layout-semantic-verify"),
        "session:layout-semantic-verify",
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
            digest(f"semantic-preservation:{final.revision_id}"),
            SemanticDecision.PRESERVED,
        )


class FakeWarningPolicy:
    def authorize(self, stage, warnings, assessment_hash, request):
        return WarningPolicyDecision(
            stage,
            True,
            tuple(item.evidence_hash for item in warnings),
            request.versions.warning_policy_version,
            digest(f"warning-policy:{stage.value}:{assessment_hash}"),
        )


def service(repository, logic_action, layout_action, renderer=None):
    return QualityOrchestrator(
        repository,
        FakeAssessment(logic_action, "logic"),
        FakeRepair(RevisionStage.LOGIC_REPAIR),
        FakeLogicVerifier(),
        FakeAssessment(layout_action, "layout"),
        FakeRepair(RevisionStage.LAYOUT_REPAIR),
        FakeLayoutRecheck(),
        FakeSemanticVerifier(),
        FakeWarningPolicy(),
        renderer or FakeRender(),
        FinalConsistencyGate(),
    )


@pytest.mark.parametrize(
    ("logic", "layout", "revision_id", "decision"),
    [
        (StageAction.CLEAN, StageAction.CLEAN, "baseline", DeliveryDecision.ACCEPT),
        (StageAction.REPAIR, StageAction.CLEAN, "logic-fixed", DeliveryDecision.ACCEPT),
        (
            StageAction.CLEAN,
            StageAction.REPAIR,
            "layout-fixed",
            DeliveryDecision.ACCEPT,
        ),
        (
            StageAction.WARNING,
            StageAction.CLEAN,
            "baseline",
            DeliveryDecision.ACCEPT_WITH_WARNING,
        ),
        (
            StageAction.CLEAN,
            StageAction.WARNING,
            "baseline",
            DeliveryDecision.ACCEPT_WITH_WARNING,
        ),
    ],
)
def test_end_to_end_quality_paths(
    tmp_path: Path,
    logic: StageAction,
    layout: StageAction,
    revision_id: str,
    decision: DeliveryDecision,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    repository.create_job("job-1", baseline())
    try:
        outcome = service(repository, logic, layout).execute(execution_request())
        assert outcome.result.decision is decision
        assert outcome.result.accepted_revision_id == revision_id
        assert outcome.snapshot.delivery_revision_id == revision_id
    finally:
        repository.close()
