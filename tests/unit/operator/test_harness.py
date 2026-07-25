from pathlib import Path

from manim_quality.agents.usage import AgentCallRecord, TokenUsage
from manim_quality.operator.agent import QualityOperatorResult
from manim_quality.operator.harness import QualityHarness
from manim_quality.operator.models import ValidationOutcome

PROBLEM = "Construct a line."
CODE = (
    f'"""{PROBLEM}"""\n'
    "class Solution(BaseConfigScene):\n"
    "    def construct(self):\n"
    "        pass\n"
)


class OperatorStub:
    def run(self, **arguments):
        session = arguments["session"]
        session.mark_solution_read("R0")
        session.record_findings(())
        session.record_layout_inspection(
            revision_id="R0",
            fingerprint="sha256:" + "1" * 64,
        )
        revision = session.submit("R0")
        return QualityOperatorResult(
            revision=revision,
            summary="clean",
            call_record=AgentCallRecord(
                run_id=arguments["run_id"],
                role="operator",
                model="model",
                prompt="prompt",
                prompt_version="v1",
                schema_version="v1",
                tool_version="v1",
                structured_output={"status": "submitted"},
                tool_calls=(),
                usage=TokenUsage(input_tokens=10, output_tokens=2),
                turns=3,
                observed_model_rounds=3,
                elapsed_ms=20,
                error=None,
            ),
        )


class Relation:
    async def check(self, request):
        return {"holds": True}


class Validator:
    def __init__(self, name: str) -> None:
        self.name = name

    async def validate(self, revision, findings, problem_hash):
        return ValidationOutcome(
            True,
            True,
            self.name,
            {"rendered": self.name == "outer"},
            revision.revision_id,
            revision.code_hash,
            problem_hash,
        )


class Layout:
    def __init__(self, name: str) -> None:
        self.name = name

    async def inspect(self, revision, problem_hash):
        return {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "blocking_count": 0,
            "issues": [],
            "verified": self.name == "outer",
        }


def test_harness_runs_operator_then_independent_gate_and_writes_pack(
    tmp_path: Path,
) -> None:
    task = tmp_path / "task"
    task.mkdir()
    output = tmp_path / "output"
    harness = QualityHarness(
        operator=OperatorStub(),
        relation_checker=Relation(),
        agent_layout_inspector=Layout("agent"),
        agent_revision_validator=Validator("agent"),
        acceptance_layout_inspector=Layout("outer"),
        acceptance_revision_validator=Validator("outer"),
    )

    result = harness.run(
        run_id="run-1",
        workspace=task,
        artifact_root=output,
        problem_text=PROBLEM,
        candidate_code=CODE,
        estimated_input_tokens=100,
        reserved_output_tokens=100,
    )

    assert result.gate_result.decision.value == "PROPOSED"
    assert result.session.submitted_revision_id == "R0"
    assert (output / "output" / "proposed_candidate.py").is_file()


def test_harness_rejects_same_agent_and_acceptance_adapter_instances() -> None:
    validator = Validator("shared")
    layout = Layout("shared")

    try:
        QualityHarness(
            operator=OperatorStub(),
            relation_checker=Relation(),
            agent_layout_inspector=layout,
            agent_revision_validator=validator,
            acceptance_layout_inspector=layout,
            acceptance_revision_validator=validator,
        )
    except ValueError as error:
        assert "independent" in str(error)
    else:
        raise AssertionError("shared validation adapters must be rejected")
