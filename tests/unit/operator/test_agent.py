import json
from pathlib import Path

import anyio
import pytest

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.profile import operator_profile
from manim_quality.agents.runtime import (
    AgentBackend,
    AgentRunFailed,
    AgentRuntime,
    BackendRequest,
    RuntimeControls,
)
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink
from manim_quality.operator.agent import QualityOperatorAgent
from manim_quality.operator.models import ValidationOutcome
from manim_quality.operator.session import QualitySession
from manim_quality.revisions.fingerprint import sha256_text

PROBLEM = "Show a line and explain its direction."
CODE = f'''"""{PROBLEM}"""
from manim import *

class Solution(BaseConfigScene):
    def construct(self):
        self.add(Line(LEFT, RIGHT))
'''


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class RelationStub:
    async def check(self, request):
        return {"holds": True}


class LayoutStub:
    async def inspect(self, revision, problem_hash):
        return {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "blocking_count": 0,
            "issues": [],
        }


class ValidatorStub:
    async def validate(self, revision, findings, problem_hash):
        return ValidationOutcome(
            True,
            True,
            "passed",
            {},
            revision.revision_id,
            revision.code_hash,
            problem_hash,
        )


class CleanScriptBackend(AgentBackend):
    def __init__(self) -> None:
        self.request: BackendRequest | None = None

    def run(self, request: BackendRequest, controls: RuntimeControls):
        self.request = request
        controls.record_round_usage(TokenUsage(input_tokens=20, output_tokens=5))
        candidate = json.loads(
            self._invoke(
                controls,
                request,
                "read_solution",
                {"revision_id": "R0"},
            )
        )
        self._invoke(controls, request, "record_findings", {"findings": []})
        self._invoke(
            controls,
            request,
            "inspect_layout",
            {"revision_id": "R0"},
        )
        self._invoke(
            controls,
            request,
            "submit_revision",
            {"revision_id": "R0"},
        )
        return controls.complete(
            {
                "status": "submitted",
                "submitted_revision_id": "R0",
                "code_hash": candidate["code_hash"],
                "problem_hash": sha256_text(PROBLEM),
                "summary": "No blocking issue found.",
            }
        )

    @staticmethod
    def _invoke(controls, request, name, arguments):
        grant = next(item for item in request.managed_tools if item.name == name)
        controls.authorize_tool(grant.sdk_name, arguments)
        return anyio.run(
            controls.execute_managed_tool,
            grant.sdk_name,
            arguments,
        )

class DirectOutputBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls):
        controls.record_round_usage(TokenUsage(input_tokens=1, output_tokens=1))
        return controls.complete(
            {
                "status": "submitted",
                "submitted_revision_id": "R0",
                "code_hash": "sha256:" + "0" * 64,
                "problem_hash": "sha256:" + "0" * 64,
                "summary": "Trust me.",
            }
        )


def limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=200_000,
        max_turns=12,
        max_tool_calls=14,
        max_elapsed_ms=30_000,
        max_input_tokens=10_000,
        max_output_tokens=2_000,
        max_cache_read_tokens=10_000,
        max_cache_write_tokens=10_000,
        max_total_tokens=20_000,
    )


def build_agent(backend, sink) -> QualityOperatorAgent:
    runtime = AgentRuntime(backend, sink, limits())
    return QualityOperatorAgent(
        runtime=runtime,
        profile=operator_profile(
            model="fake-model",
            prompt_version="quality-operator-v1",
        ),
    )


def test_operator_runs_clean_candidate_through_tools_without_prompt_source(
    tmp_path: Path,
) -> None:
    backend = CleanScriptBackend()
    sink = MemorySink()
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    agent = build_agent(backend, sink)

    result = agent.run(
        run_id="operator-1",
        workspace=tmp_path,
        session=session,
        relation_checker=RelationStub(),
        layout_inspector=LayoutStub(),
        revision_validator=ValidatorStub(),
        estimated_input_tokens=100,
        reserved_output_tokens=100,
    )

    assert result.revision.revision_id == "R0"
    assert result.summary == "No blocking issue found."
    assert session.submitted_revision_id == "R0"
    assert backend.request is not None
    assert backend.request.allowed_tools == ("Agent",)
    assert len(backend.request.managed_tools) == 7
    assert {item.name for item in backend.request.subagents} == {
        "math_geometry_reviewer",
        "animation_lifecycle_reviewer",
    }
    assert CODE not in backend.request.prompt
    assert sink.records[0].role == "operator"


def test_operator_rejects_structured_output_without_tool_submission(
    tmp_path: Path,
) -> None:
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    agent = build_agent(DirectOutputBackend(), MemorySink())

    with pytest.raises(AgentRunFailed, match="submit_revision"):
        agent.run(
            run_id="operator-bypass",
            workspace=tmp_path,
            session=session,
            relation_checker=RelationStub(),
            layout_inspector=LayoutStub(),
            revision_validator=ValidatorStub(),
            estimated_input_tokens=100,
            reserved_output_tokens=100,
        )

    assert session.submitted_revision_id is None


def test_terminal_output_supports_honest_held_state() -> None:
    from manim_quality.operator.agent import _bind_output
    from manim_quality.operator.session import QualitySession

    problem = "Problem: prove AB is parallel to CD."
    code = (
        f'"""{problem}"""\n'
        "from manim import *\n\n"
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        self.add(Line(LEFT, RIGHT))\n"
    )
    session = QualitySession(problem_text=problem, candidate_code=code)

    summary = _bind_output(
        {
            "status": "held",
            "summary": "预算耗尽，仍剩 1 个 blocking。",
            "hold_reason": "patch budget exhausted with blocking overlap",
        },
        session,
    )
    assert "blocking" in summary or summary

    with pytest.raises(ValueError, match="hold_reason"):
        _bind_output({"status": "held", "summary": "x"}, session)

    with pytest.raises(ValueError, match="allows only"):
        _bind_output(
            {
                "status": "held",
                "summary": "x",
                "hold_reason": "y",
                "submitted_revision_id": "R1",
            },
            session,
        )


def test_held_terminal_result_propagates_hold_reason() -> None:
    from types import SimpleNamespace

    from manim_quality.agents.usage import AgentCallRecord, TokenUsage
    from manim_quality.operator.agent import _terminal_result
    from manim_quality.operator.session import QualitySession

    problem = "Problem: prove AB is parallel to CD."
    code = (
        f'"""{problem}"""\n'
        "from manim import *\n\n"
        "class Solution(BaseConfigScene):\n"
        "    def construct(self):\n"
        "        self.add(Line(LEFT, RIGHT))\n"
    )
    session = QualitySession(problem_text=problem, candidate_code=code)
    record = AgentCallRecord(
        run_id="r",
        role="quality_operator",
        model="m",
        prompt="p",
        prompt_version="v",
        schema_version="v",
        tool_version="v",
        structured_output=None,
        tool_calls=(),
        usage=TokenUsage(),
        turns=1,
        observed_model_rounds=1,
        elapsed_ms=1,
        error=None,
    )
    result = SimpleNamespace(
        structured_output={
            "status": "held",
            "summary": "预算耗尽仍剩 blocking。",
            "hold_reason": "blocking overlap not cleared within budget",
        },
        record=record,
        sdk_messages=(),
        subagent_results=(),
    )

    outcome = _terminal_result(session, result)

    assert outcome.agent_held is True
    assert outcome.hold_reason == "blocking overlap not cleared within budget"
