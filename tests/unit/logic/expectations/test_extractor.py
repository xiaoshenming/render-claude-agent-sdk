from pathlib import Path

from manim_quality.agents import (
    AgentRuntime,
    BudgetLimits,
    reviewer_profile,
)
from manim_quality.agents.runtime import (
    AgentBackend,
    BackendRequest,
    BackendResult,
    RuntimeControls,
)
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink
from manim_quality.logic.expectations.extractor import ExpectedRelationExtractor


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class ContractBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        assert "candidate.py" not in request.prompt
        assert request.editable_paths == ()
        controls.record_round_usage(TokenUsage(input_tokens=100, output_tokens=40))
        controls.authorize_tool("Read", {"file_path": request.readable_paths[0]})
        return controls.complete(
            {
                "schema_version": "manim-quality.expected-relations.v1",
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "relation": "perpendicular",
                        "operands": ["AD", "BC"],
                        "source_kind": "problem",
                        "evidence": "AD is perpendicular to BC at D",
                        "confidence": "explicit",
                    }
                ],
            }
        )


def limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=20_000,
        max_turns=2,
        max_tool_calls=3,
        max_elapsed_ms=10_000,
        max_input_tokens=2_000,
        max_output_tokens=1_000,
        max_cache_read_tokens=2_000,
        max_cache_write_tokens=2_000,
        max_total_tokens=4_000,
    )


def test_extracts_contract_through_read_only_agent_runtime(tmp_path: Path) -> None:
    problem = tmp_path / "problem_text.txt"
    problem.write_text("AD is perpendicular to BC at D.", encoding="utf-8")
    sink = MemorySink()
    extractor = ExpectedRelationExtractor(
        runtime=AgentRuntime(ContractBackend(), sink, limits()),
        profile=reviewer_profile(
            model="fake-model", prompt_version="expected-relations-v1"
        ),
    )

    result = extractor.extract(
        run_id="extract-1",
        workspace=tmp_path,
        source_path=problem,
        estimated_input_tokens=200,
        reserved_output_tokens=500,
    )

    assert result.contract.claims[0].relation == "perpendicular"
    assert result.call_record.role == "reviewer"


def test_prompt_asks_for_explicit_facts_not_repairs(tmp_path: Path) -> None:
    problem = tmp_path / "problem_text.txt"
    problem.write_text("Connect A to D.", encoding="utf-8")
    extractor = ExpectedRelationExtractor(
        runtime=AgentRuntime(ContractBackend(), MemorySink(), limits()),
        profile=reviewer_profile(
            model="fake-model", prompt_version="expected-relations-v1"
        ),
    )

    prompt = extractor.build_prompt(problem)

    assert "line_endpoints" in prompt
    assert "point_coordinate" in prompt
    assert "segment_length" in prompt
    assert "intersection" in prompt
    assert "source quote" in prompt
    assert "Do not diagnose" in prompt
    assert "repair" not in prompt.lower()
