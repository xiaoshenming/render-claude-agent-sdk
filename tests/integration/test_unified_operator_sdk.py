import json
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
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
REVIEWERS = ("math_geometry_reviewer", "animation_lifecycle_reviewer")
REVIEWER_RESULT = json.dumps(
    {
        "decision": "pass",
        "diagnosis": "No supported defect.",
        "issues": [],
        "coverage": {"diagrams": ["main"]},
        "confidence": 0.9,
    },
    separators=(",", ":"),
)


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
        self.server = options.mcp_servers["quality"]["instance"]
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


async def _reviewer_round(driver, index, reviewer):
    agent_id = f"reviewer-id-{index}"
    tool_id = f"agent-tool-{index}"
    agent_input = {
        "subagent_type": reviewer,
        "description": "Audit the current Solution",
        "prompt": "Audit the current Solution and return findings.",
        "run_in_background": False,
    }
    agent_data = await driver.allow("Agent", agent_input, tool_id)
    yield _message(tool_id, "Agent", agent_input, f"agent-message-{index}")
    await driver.start(
        driver.lifecycle_data("SubagentStart", reviewer, agent_id),
        None,
        {"signal": None},
    )
    read_args = {"revision_id": "R0"}
    child_data = await driver.allow(
        "mcp__quality__read_solution",
        read_args,
        f"agent-read-{index}",
        agent_id=agent_id,
        agent_type=reviewer,
    )
    await driver.invoke("read_solution", read_args)
    yield _message(
        f"agent-read-{index}",
        "mcp__quality__read_solution",
        read_args,
        f"agent-child-{index}",
        parent_tool_use_id=tool_id,
    )
    await driver.finish(child_data)
    await driver.stop(
        driver.lifecycle_data(
            "SubagentStop",
            reviewer,
            agent_id,
            stop_hook_active=False,
            agent_transcript_path="ignored",
        ),
        None,
        {"signal": None},
    )
    yield UserMessage(
        content=[
            ToolResultBlock(
                tool_use_id=tool_id,
                content=REVIEWER_RESULT,
                is_error=False,
            )
        ],
        parent_tool_use_id=None,
    )
    await driver.finish(agent_data)


async def _structured_output(driver, session):
    output = {
        "status": "submitted",
        "submitted_revision_id": "R0",
        "code_hash": session.baseline.code_hash,
        "problem_hash": session.problem_hash,
        "summary": "No blocking issue found.",
    }
    data = await driver.allow("StructuredOutput", output, "structured-1")
    yield _message("structured-1", "StructuredOutput", output, "message-7")
    await driver.finish(data)
    yield ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=7,
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
        parent_script = (
            (1, "read_solution", {"revision_id": "R0"}),
            (4, "record_findings", {"findings": []}),
            (5, "inspect_layout", {"revision_id": "R0"}),
            (6, "submit_revision", {"revision_id": "R0"}),
        )
        for index, name, arguments in parent_script[:1]:
            async for message in _parent_tool(driver, index, name, arguments):
                yield message
        for index, reviewer in enumerate(REVIEWERS, start=1):
            async for message in _reviewer_round(driver, index, reviewer):
                yield message
        for index, name, arguments in parent_script[1:]:
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
    assert result.call_record.turns == 7
    assert len(result.call_record.tool_calls) == 9
    assert len(result.subagent_results) == 2
    assert {item["agent_type"] for item in result.subagent_results} == set(REVIEWERS)
    assert session.submitted_revision_id == "R0"
