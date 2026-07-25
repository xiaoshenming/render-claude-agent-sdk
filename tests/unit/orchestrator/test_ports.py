import pytest

from manim_quality.contracts import RevisionStage
from manim_quality.delivery.consistency_gate import FinalConsistencyGate
from manim_quality.orchestrator.identity import ComponentIdentity, ComponentRole
from manim_quality.orchestrator.models import StageAction
from manim_quality.orchestrator.ports import (
    LayoutDetectionPort,
    LayoutRecheckPort,
    LayoutRepairPort,
    LayoutSemanticVerificationPort,
    LogicRepairPort,
    LogicReviewPort,
    LogicVerificationPort,
    RenderStage,
    WarningPolicyPort,
)
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


def test_production_and_verification_ports_are_separate_capabilities() -> None:
    assert _operations(LogicReviewPort) == {"assess"}
    assert _operations(LogicRepairPort) == {"propose"}
    assert _operations(LogicVerificationPort) == {"verify"}
    assert _operations(LayoutDetectionPort) == {"assess"}
    assert _operations(LayoutRepairPort) == {"propose"}
    assert _operations(LayoutRecheckPort) == {"verify"}
    assert _operations(LayoutSemanticVerificationPort) == {"verify"}
    assert _operations(WarningPolicyPort) == {"authorize"}
    assert _operations(RenderStage) == {"bind", "render"}


@pytest.mark.parametrize(
    ("port_name", "operation", "role"),
    [
        ("logic_review", "assess", None),
        ("logic_repair", "propose", ComponentRole.LOGIC_REPAIR),
        ("logic_verify", "verify", ComponentRole.LOGIC_VERIFY),
        ("layout_detect", "assess", None),
        ("layout_repair", "propose", ComponentRole.LAYOUT_REPAIR),
        ("layout_recheck", "verify", ComponentRole.LAYOUT_RECHECK),
        (
            "layout_semantic_verify",
            "verify",
            ComponentRole.LAYOUT_SEMANTIC_VERIFY,
        ),
        ("warning_policy", "authorize", None),
        ("renderer", "render", None),
        ("renderer", "bind", None),
    ],
)
def test_constructor_rejects_port_missing_required_operation(
    port_name: str, operation: str, role: ComponentRole | None
) -> None:
    repository = SQLiteRevisionRepository(":memory:")
    components = _valid_components()
    components[port_name] = _without_operation(port_name, operation, role)
    try:
        with pytest.raises(
            TypeError, match=rf"{port_name}\.{operation} must be callable"
        ):
            QualityOrchestrator(
                repository,
                **components,
                gate=FinalConsistencyGate(),
            )
    finally:
        repository.close()


def _operations(port: type) -> set[str]:
    return {
        name
        for name, value in vars(port).items()
        if not name.startswith("_") and callable(value)
    }


def _valid_components() -> dict[str, object]:
    return {
        "logic_review": FakeAssessment(StageAction.CLEAN, "logic"),
        "logic_repair": FakeRepair(RevisionStage.LOGIC_REPAIR),
        "logic_verify": FakeLogicVerifier(),
        "layout_detect": FakeAssessment(StageAction.CLEAN, "layout"),
        "layout_repair": FakeRepair(RevisionStage.LAYOUT_REPAIR),
        "layout_recheck": FakeLayoutRecheck(),
        "layout_semantic_verify": FakeSemanticVerifier(),
        "warning_policy": FakeWarningPolicy(),
        "renderer": FakeRender(),
    }


def _without_operation(
    port_name: str, operation: str, role: ComponentRole | None
) -> object:
    component = type("MissingOperation", (), {})()
    if role is not None:
        component.identity = ComponentIdentity(
            role,
            f"missing-{port_name}",
            digest(f"profile:missing-{port_name}"),
            f"session:missing-{port_name}",
        )
    if port_name == "renderer":
        other = "bind" if operation == "render" else "render"
        setattr(component, other, lambda *args: None)
    return component
