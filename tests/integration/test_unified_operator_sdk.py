from pathlib import Path

from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock
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


def test_real_sdk_backend_runs_clean_operator_tool_sequence(
    tmp_path: Path,
) -> None:
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    script = (
        ("read_problem", {}),
        (
            "read_candidate",
            {"revision_id": "R0", "start_line": 1, "end_line": 100},
        ),
        ("record_findings", {"findings": []}),
        ("inspect_layout", {"revision_id": "R0"}),
        ("submit_revision", {"revision_id": "R0"}),
    )

    async def fake_query(*, prompt, options):
        pre = options.hooks["PreToolUse"][0].hooks[0]
        post = options.hooks["PostToolUse"][0].hooks[0]
        server = options.mcp_servers["quality"]["instance"]
        handler = server.request_handlers[CallToolRequest]
        for index, (name, arguments) in enumerate(script, start=1):
            sdk_name = f"mcp__quality__{name}"
            tool_id = f"tool-{index}"
            hook_input = {
                "hook_event_name": "PreToolUse",
                "session_id": "sdk-session",
                "transcript_path": "ignored",
                "cwd": str(tmp_path),
                "tool_name": sdk_name,
                "tool_input": arguments,
                "tool_use_id": tool_id,
            }
            permission = await pre(hook_input, tool_id, {"signal": None})
            assert permission["hookSpecificOutput"]["permissionDecision"] == "allow"
            await handler(
                CallToolRequest(params={"name": name, "arguments": arguments})
            )
            yield AssistantMessage(
                content=[ToolUseBlock(id=tool_id, name=sdk_name, input=arguments)],
                model="fake-model",
                message_id=f"message-{index}",
                usage={"input_tokens": 1, "output_tokens": 1},
            )
            await post(
                hook_input | {"hook_event_name": "PostToolUse", "tool_response": {}},
                tool_id,
                {"signal": None},
            )
        output = {
            "status": "submitted",
            "submitted_revision_id": "R0",
            "code_hash": session.baseline.code_hash,
            "problem_hash": session.problem_hash,
            "summary": "No blocking issue found.",
        }
        tool_id = "structured-1"
        hook_input = {
            "hook_event_name": "PreToolUse",
            "session_id": "sdk-session",
            "transcript_path": "ignored",
            "cwd": str(tmp_path),
            "tool_name": "StructuredOutput",
            "tool_input": output,
            "tool_use_id": tool_id,
        }
        await pre(hook_input, tool_id, {"signal": None})
        yield AssistantMessage(
            content=[
                ToolUseBlock(id=tool_id, name="StructuredOutput", input=output)
            ],
            model="fake-model",
            message_id="message-6",
            usage={"input_tokens": 1, "output_tokens": 1},
        )
        await post(
            hook_input | {"hook_event_name": "PostToolUse", "tool_response": {}},
            tool_id,
            {"signal": None},
        )
        yield ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=6,
            session_id="sdk-session",
            usage={"input_tokens": 6, "output_tokens": 6},
            structured_output=output,
        )

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
    assert result.call_record.turns == 6
    assert len(result.call_record.tool_calls) == 6
    assert session.submitted_revision_id == "R0"
