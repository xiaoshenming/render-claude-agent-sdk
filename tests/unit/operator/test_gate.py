import anyio

from manim_quality.operator.gate import GateDecision, OuterAcceptanceGate
from manim_quality.operator.models import (
    Finding,
    FindingCategory,
    PatchScope,
    ValidationOutcome,
)
from manim_quality.operator.session import QualitySession

PROBLEM = "Construct a line."
CODE = f'''"""{PROBLEM}"""
from manim import *

class Solution(BaseConfigScene):
    def construct(self):
        self.add(Line(LEFT, RIGHT))
'''


class Validator:
    def __init__(
        self,
        *,
        passed: bool,
        rendered: bool = True,
        stale: bool = False,
    ) -> None:
        self.passed = passed
        self.rendered = rendered
        self.stale = stale
        self.calls = 0

    async def validate(self, revision, findings, problem_hash):
        self.calls += 1
        return ValidationOutcome(
            passed=self.passed,
            improved=self.passed,
            summary="independent full validation",
            details={"rendered": self.rendered},
            revision_id="OTHER" if self.stale else revision.revision_id,
            code_hash=revision.code_hash,
            problem_hash=problem_hash,
        )


class Layout:
    def __init__(self, blocking_count: int, *, stale: bool = False) -> None:
        self.blocking_count = blocking_count
        self.stale = stale
        self.calls = 0

    async def inspect(self, revision, problem_hash):
        self.calls += 1
        return {
            "revision_id": "OTHER" if self.stale else revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "blocking_count": self.blocking_count,
            "issues": [],
            "verified": True,
        }


def submitted_session() -> QualitySession:
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    session.mark_solution_read("R0")
    session.record_findings(())
    session.record_layout_inspection(
        revision_id="R0",
        fingerprint="sha256:" + "1" * 64,
    )
    session.submit("R0")
    return session


def test_outer_gate_accepts_only_independently_clean_submission() -> None:
    validator = Validator(passed=True)
    layout = Layout(blocking_count=0)
    gate = OuterAcceptanceGate(
        revision_validator=validator,
        layout_inspector=layout,
    )

    result = anyio.run(gate.evaluate, submitted_session())

    assert result.decision is GateDecision.PROPOSED
    assert result.final_revision.revision_id == "R0"
    assert result.rollback_revision is None
    assert validator.calls == 1
    assert layout.calls == 1


def test_outer_gate_rejects_agent_submission_when_validation_fails() -> None:
    gate = OuterAcceptanceGate(
        revision_validator=Validator(passed=False),
        layout_inspector=Layout(blocking_count=0),
    )

    result = anyio.run(gate.evaluate, submitted_session())

    assert result.decision is GateDecision.HOLD
    assert result.final_revision is None
    assert result.rollback_revision.revision_id == "R0"
    assert "independent_validation_failed" in result.reasons


def test_outer_gate_keeps_rendered_source_with_bbox_follow_up() -> None:
    gate = OuterAcceptanceGate(
        revision_validator=Validator(passed=True),
        layout_inspector=Layout(blocking_count=2),
    )

    result = anyio.run(gate.evaluate, submitted_session())

    assert result.decision is GateDecision.PROPOSED
    assert result.final_revision.revision_id == "R0"
    assert result.rollback_revision is None
    assert result.layout_report["blocking_count"] == 2


def test_outer_gate_fails_closed_on_malformed_layout_report() -> None:
    gate = OuterAcceptanceGate(
        revision_validator=Validator(passed=True),
        layout_inspector=Layout(blocking_count=-1),
    )

    result = anyio.run(gate.evaluate, submitted_session())

    assert result.decision is GateDecision.HOLD
    assert "invalid_layout_report" in result.reasons


def test_outer_gate_does_not_accept_compile_only_validation() -> None:
    gate = OuterAcceptanceGate(
        revision_validator=Validator(passed=True, rendered=False),
        layout_inspector=Layout(blocking_count=0),
    )

    result = anyio.run(gate.evaluate, submitted_session())

    assert result.decision is GateDecision.HOLD
    assert "full_render_not_verified" in result.reasons


def test_outer_gate_rejects_stale_revision_evidence() -> None:
    gate = OuterAcceptanceGate(
        revision_validator=Validator(passed=True, stale=True),
        layout_inspector=Layout(blocking_count=0),
    )

    result = anyio.run(gate.evaluate, submitted_session())

    assert result.decision is GateDecision.HOLD
    assert "validation_identity_mismatch" in result.reasons


def test_outer_gate_rejects_stale_layout_evidence() -> None:
    gate = OuterAcceptanceGate(
        revision_validator=Validator(passed=True),
        layout_inspector=Layout(blocking_count=0, stale=True),
    )

    result = anyio.run(gate.evaluate, submitted_session())

    assert result.decision is GateDecision.HOLD
    assert "layout_identity_mismatch" in result.reasons


def test_outer_gate_rejects_deleted_scene_even_when_services_pass() -> None:
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    session.mark_solution_read("R0")
    session.record_findings(
        (
            Finding(
                finding_id="logic-warning",
                category=FindingCategory.LOGIC,
                severity="warning",
                summary="Review the scene construction.",
                acceptance_criteria="The scene remains complete.",
            ),
        )
    )
    revision = session.apply_patch(
        scope=PatchScope.LOGIC,
            old_text=(
                "class Solution(BaseConfigScene):\n"
                "    def construct(self):\n"
                "        self.add(Line(LEFT, RIGHT))"
            ),
            new_text=(
                "class Solution(BaseConfigScene):\n"
                "    def construct(self):\n"
                "        pass"
            ),
        finding_ids=("logic-warning",),
    )
    session.record_validation(
        revision_id=revision.revision_id,
        passed=True,
        improved=True,
        fingerprint="sha256:" + "2" * 64,
    )
    session.record_layout_inspection(
        revision_id=revision.revision_id,
        fingerprint="sha256:" + "3" * 64,
    )
    session.submit(revision.revision_id)
    gate = OuterAcceptanceGate(
        revision_validator=Validator(passed=True),
        layout_inspector=Layout(blocking_count=0),
    )

    result = anyio.run(gate.evaluate, session)

    assert result.decision is GateDecision.HOLD
    assert "excessive_executable_call_deletion" in result.reasons
