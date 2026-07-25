import pytest

from manim_quality.contracts import RevisionStage
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.identity import ComponentIdentity, ComponentRole
from manim_quality.orchestrator.models import StageAction
from manim_quality.orchestrator.service import QualityOrchestrator
from manim_quality.storage.database import SQLiteRevisionRepository
from tests.e2e.test_quality_happy_path import (
    FakeAssessment,
    FakeLayoutRecheck,
    FakeLogicVerifier,
    FakeRender,
    FakeRepair,
    FakeSemanticVerifier,
    FakeWarningPolicy,
    digest,
)


class DeclaredComponent:
    def __init__(self, identity: ComponentIdentity) -> None:
        self.identity = identity

    def propose(self, *args):
        raise AssertionError("constructor test must not execute propose")

    def verify(self, *args):
        raise AssertionError("constructor test must not execute verify")


def identity(role: ComponentRole, component_id: str, session_scope: str):
    return ComponentIdentity(
        role, component_id, digest("shared-profile"), session_scope
    )


def orchestrator(repository, logic_repair, logic_verify):
    return QualityOrchestrator(
        repository,
        FakeAssessment(StageAction.CLEAN, "logic"),
        logic_repair,
        logic_verify,
        FakeAssessment(StageAction.CLEAN, "layout"),
        FakeRepair(RevisionStage.LAYOUT_REPAIR),
        FakeLayoutRecheck(),
        FakeSemanticVerifier(),
        FakeWarningPolicy(),
        FakeRender(),
        FinalConsistencyGate(),
    )


def test_logic_repair_and_verifier_cannot_be_same_runtime_component() -> None:
    repository = SQLiteRevisionRepository(":memory:")
    multi_role = DeclaredComponent(
        identity(ComponentRole.LOGIC_REPAIR, "multi-role", "multi-role-session")
    )
    try:
        with pytest.raises(ValueError, match="logic repair and verifier"):
            QualityOrchestrator(
                repository,
                FakeAssessment(StageAction.CLEAN, "logic"),
                multi_role,
                multi_role,
                FakeAssessment(StageAction.CLEAN, "layout"),
                FakeRepair(RevisionStage.LAYOUT_REPAIR),
                FakeLayoutRecheck(),
                FakeSemanticVerifier(),
                FakeWarningPolicy(),
                FakeRender(),
                FinalConsistencyGate(),
            )
    finally:
        repository.close()


def test_component_role_must_match_injected_port() -> None:
    repository = SQLiteRevisionRepository(":memory:")
    wrong_role = DeclaredComponent(
        identity(ComponentRole.LOGIC_VERIFY, "logic-repair", "logic-repair-session")
    )
    try:
        with pytest.raises(ValueError, match="expected role LOGIC_REPAIR"):
            orchestrator(repository, wrong_role, FakeLogicVerifier())
    finally:
        repository.close()


def test_distinct_wrappers_cannot_share_component_identity() -> None:
    repository = SQLiteRevisionRepository(":memory:")
    repair = DeclaredComponent(
        identity(ComponentRole.LOGIC_REPAIR, "shared-backend", "repair-session")
    )
    verifier = DeclaredComponent(
        identity(ComponentRole.LOGIC_VERIFY, "shared-backend", "verify-session")
    )
    try:
        with pytest.raises(ValueError, match="duplicate component_id"):
            orchestrator(repository, repair, verifier)
    finally:
        repository.close()


def test_distinct_components_cannot_share_session_scope() -> None:
    repository = SQLiteRevisionRepository(":memory:")
    repair = DeclaredComponent(
        identity(ComponentRole.LOGIC_REPAIR, "logic-repair", "shared-session")
    )
    verifier = DeclaredComponent(
        identity(ComponentRole.LOGIC_VERIFY, "logic-verify", "shared-session")
    )
    try:
        with pytest.raises(ValueError, match="duplicate session_scope"):
            orchestrator(repository, repair, verifier)
    finally:
        repository.close()


def test_roles_may_share_profile_when_sessions_are_isolated() -> None:
    repository = SQLiteRevisionRepository(":memory:")
    repair = DeclaredComponent(
        identity(ComponentRole.LOGIC_REPAIR, "logic-repair", "repair-session")
    )
    verifier = DeclaredComponent(
        identity(ComponentRole.LOGIC_VERIFY, "logic-verify", "verify-session")
    )
    try:
        orchestrator(repository, repair, verifier)
    finally:
        repository.close()


@pytest.mark.parametrize("shared_roles", [("recheck",), ("semantic",)])
def test_layout_repair_cannot_share_runtime_with_verifiers(shared_roles) -> None:
    repository = SQLiteRevisionRepository(":memory:")
    multi_role = DeclaredComponent(
        identity(ComponentRole.LAYOUT_REPAIR, "multi-role", "multi-role-session")
    )
    recheck = multi_role if shared_roles == ("recheck",) else FakeLayoutRecheck()
    semantic = multi_role if shared_roles == ("semantic",) else FakeSemanticVerifier()
    try:
        with pytest.raises(ValueError, match="layout repair"):
            QualityOrchestrator(
                repository,
                FakeAssessment(StageAction.CLEAN, "logic"),
                FakeRepair(RevisionStage.LOGIC_REPAIR),
                FakeLogicVerifier(),
                FakeAssessment(StageAction.CLEAN, "layout"),
                multi_role,
                recheck,
                semantic,
                FakeWarningPolicy(),
                FakeRender(),
                FinalConsistencyGate(),
            )
    finally:
        repository.close()
