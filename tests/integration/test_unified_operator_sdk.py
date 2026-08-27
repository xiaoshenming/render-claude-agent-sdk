from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    ToolUseBlock,
)
from mcp.types import CallToolRequest

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.profile import operator_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import AgentCallRecord, UsageSink
from manim_quality.operator.agent import QualityOperatorAgent
from manim_quality.operator.models import ValidationOutcome
from manim_quality.operator.session import QualitySession

PROBLEM = "Construct a line."
CODE = (
    f'"""{PROBLEM}"""\n'
    "class Solution(BaseConfigScene):\n"
    "    def construct(self):\n"
    "        self.wait()\n"
)
REVIEWERS = (
    "math_geometry_reviewer",
    "animation_lifecycle_reviewer",
    "visual_layout_reviewer",
)
REVIEWER_RESULT = {
    "decision": "pass",
    "diagnosis": "No supported defect.",
    "issues": [],
    "coverage": {"summary": "complete", "checked_items": ["Solution"]},
    "confidence": 0.9,
}


class Sink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class Relation:
    async def check(self, request):
        return {"verified": True, "holds": True}


class Layout:
    async def inspect(self, revision, problem_hash):
        return {
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": problem_hash,
            "verified": True,
            "blocking_count": 0,
            "issues": [],
        }


class Validator:
    async def validate(self, revision, findings, problem_hash):
        return ValidationOutcome(
            True,
            True,
            "passed",
            {"rendered": True},
            revision.revision_id,
            revision.code_hash,
            problem_hash,
        )


def limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=200_000,
        max_turns=12,
        max_tool_calls=14,
        max_elapsed_ms=30_000,
        max_input_tokens=1_000,
        max_output_tokens=1_000,
        max_cache_read_tokens=1_000,
        max_cache_write_tokens=1_000,
        max_total_tokens=3_000,
    )


class _SdkDriver:
    """Drive the mounted hooks and MCP server exactly as the SDK would."""

    def __init__(self, options, cwd: str) -> None:
        self.pre = options.hooks["PreToolUse"][0].hooks[0]
        self.post = options.hooks["PostToolUse"][0].hooks[0]
        self.start = options.hooks["SubagentStart"][0].hooks[0]
        self.stop = options.hooks["SubagentStop"][0].hooks[0]
        quality = options.mcp_servers.get("quality")
        self.server = quality["instance"] if quality else None
        self.cwd = cwd

    def hook_data(self, name, arguments, tool_id, **extra):
        return {
            "hook_event_name": "PreToolUse",
            "session_id": "sdk-session",
            "transcript_path": "ignored",
            "cwd": self.cwd,
            "tool_name": name,
            "tool_input": arguments,
            "tool_use_id": tool_id,
            **extra,
        }

    async def allow(self, name, arguments, tool_id, **extra):
        data = self.hook_data(name, arguments, tool_id, **extra)
        permission = await self.pre(data, tool_id, {"signal": None})
        assert permission["hookSpecificOutput"]["permissionDecision"] == "allow"
        return data

    async def invoke(self, name, arguments) -> None:
        await self.server.request_handlers[CallToolRequest](
            CallToolRequest(params={"name": name, "arguments": arguments})
        )

    async def finish(self, data) -> None:
        await self.post(
            data | {"hook_event_name": "PostToolUse", "tool_response": {}},
            data["tool_use_id"],
            {"signal": None},
        )

    def lifecycle_data(self, event, reviewer, agent_id, **extra):
        return {
            "hook_event_name": event,
            "session_id": "sdk-session",
            "transcript_path": "ignored",
            "cwd": self.cwd,
            "agent_id": agent_id,
            "agent_type": reviewer,
            **extra,
        }


def _message(tool_id, name, arguments, message_id, **extra):
    return AssistantMessage(
        content=[ToolUseBlock(id=tool_id, name=name, input=arguments)],
        model="fake-model",
        message_id=message_id,
        usage={"input_tokens": 2, "output_tokens": 1},
        **extra,
    )


async def _parent_tool(driver, index, name, arguments):
    sdk_name = f"mcp__quality__{name}"
    tool_id = f"tool-{index}"
    data = await driver.allow(sdk_name, arguments, tool_id)
    await driver.invoke(name, arguments)
    yield _message(tool_id, sdk_name, arguments, f"message-{index}")
    await driver.finish(data)


async def _native_tool(
    driver,
    index,
    name,
    arguments,
    *,
    parent_tool_use_id=None,
    **extra,
):
    tool_id = f"native-{index}"
    data = await driver.allow(name, arguments, tool_id, **extra)
    yield _message(
        tool_id,
        name,
        arguments,
        f"native-message-{index}",
        parent_tool_use_id=parent_tool_use_id,
    )
    await driver.finish(data)


async def _parallel_reviewer_output(driver):
    args = {"revision_id": "R0"}
    async for message in _parent_tool(driver, 1, "read_solution", args):
        yield message
    data = await driver.allow("StructuredOutput", REVIEWER_RESULT, "review-output")
    yield _message(
        "review-output", "StructuredOutput", REVIEWER_RESULT, "review-message"
    )
    await driver.finish(data)
    yield ResultMessage(
        subtype="success", duration_ms=30, duration_api_ms=20,
        is_error=False, num_turns=2, session_id="review-session",
        usage={"input_tokens": 20, "output_tokens": 10},
        structured_output=REVIEWER_RESULT,
    )


async def _structured_output(driver, session):
    output = {
        "status": "submitted",
        "submitted_revision_id": "R0",
        "code_hash": session.baseline.code_hash,
        "problem_hash": session.problem_hash,
        "summary": "No blocking issue found.",
    }
    data = await driver.allow("StructuredOutput", output, "structured-1")
    yield _message("structured-1", "StructuredOutput", output, "message-8")
    await driver.finish(data)
    yield ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=8,
        session_id="sdk-session",
        usage={"input_tokens": 40, "output_tokens": 20},
        structured_output=output,
    )


def test_real_sdk_backend_runs_clean_operator_tool_sequence(
    tmp_path: Path,
) -> None:
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)

    async def fake_query(*, prompt, options):
        driver = _SdkDriver(options, str(tmp_path))
        candidates = tuple(tmp_path.glob(".quality-agent-session-*/candidate.py"))
        candidate = candidates[0] if candidates else tmp_path / "candidate.py"
        if "mcp__quality__read_solution" in options.allowed_tools:
            async for message in _parallel_reviewer_output(driver):
                yield message
            return
        parent_script = (
            (2, "record_findings", {"findings": []}),
            (3, "validate_revision", {"revision_id": "R0", "finding_ids": []}),
            (4, "inspect_layout", {"revision_id": "R0", "finding_ids": []}),
            (5, "submit_revision", {"revision_id": "R0"}),
        )
        async for message in _native_tool(
            driver, 1, "Read", {"file_path": str(candidate)}
        ):
            yield message
        for index, name, arguments in parent_script:
            async for message in _parent_tool(driver, index, name, arguments):
                yield message
        async for message in _structured_output(driver, session):
            yield message

    sink = Sink()
    runtime = AgentRuntime(
        ClaudeSdkBackend(query_func=fake_query),
        sink,
        limits(),
    )
    agent = QualityOperatorAgent(
        runtime=runtime,
        profile=operator_profile(
            model="fake-model",
            prompt_version="quality-operator-v1",
        ),
    )

    result = agent.run(
        run_id="sdk-e2e",
        workspace=tmp_path,
        session=session,
        relation_checker=Relation(),
        layout_inspector=Layout(),
        revision_validator=Validator(),
        estimated_input_tokens=10,
        reserved_output_tokens=10,
    )

    assert result.revision.revision_id == "R0"
    assert result.call_record.turns == 14
    assert len(result.call_record.tool_calls) == 12
    assert len(result.subagent_results) == 3
    assert {item["agent_type"] for item in result.subagent_results} == set(REVIEWERS)
    assert session.submitted_revision_id == "R0"
