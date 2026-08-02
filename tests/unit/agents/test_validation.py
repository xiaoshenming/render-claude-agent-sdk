from pathlib import Path

import pytest

from manim_quality.agents._runtime_models import AgentRunFailed, AgentRunRequest
from manim_quality.agents.budget import BudgetLimits, BudgetTracker
from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect
from manim_quality.agents.profile import AgentProfile, AgentRole, reviewer_profile
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, ToolCallRecord


def limits(**changes: int) -> BudgetLimits:
    values = {name: 10 for name in BudgetLimits.__dataclass_fields__}
    values.update(changes)
    return BudgetLimits(**values)


def call_record(**changes: object) -> AgentCallRecord:
    values: dict[str, object] = {
        "run_id": "run-1",
        "role": "reviewer",
        "model": "model",
        "prompt": "review",
        "prompt_version": "prompt-v1",
        "schema_version": "schema-v1",
        "tool_version": "tools-v1",
        "structured_output": None,
        "tool_calls": (),
        "usage": TokenUsage(),
        "turns": 0,
        "observed_model_rounds": 0,
        "elapsed_ms": 0,
        "error": None,
    }
    values.update(changes)
    return AgentCallRecord(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_budget_limits_require_positive_integers(value: object) -> None:
    values: dict[str, object] = {name: 10 for name in BudgetLimits.__dataclass_fields__}
    values["max_turns"] = value

    with pytest.raises(ValueError, match="positive integer"):
        BudgetLimits(**values)  # type: ignore[arg-type]


def test_budget_tracker_rejects_invalid_inputs() -> None:
    with pytest.raises(TypeError, match="BudgetLimits"):
        BudgetTracker(object())  # type: ignore[arg-type]

    tracker = BudgetTracker(limits())
    with pytest.raises(ValueError, match="non-negative"):
        tracker.check_context(-1)
    with pytest.raises(TypeError, match="TokenUsage"):
        tracker.record_usage(object())  # type: ignore[arg-type]


def test_agent_request_rejects_invalid_identity_profile_and_counts(
    tmp_path: Path,
) -> None:
    profile = reviewer_profile(model="model", prompt_version="v1")
    common = {
        "run_id": "run-1",
        "profile": profile,
        "prompt": "review",
        "output_schema": {"type": "object"},
        "workspace": tmp_path,
        "readable_paths": (),
        "editable_paths": (),
        "context_bytes": 0,
        "estimated_input_tokens": 0,
        "reserved_output_tokens": 0,
        "reserved_cache_read_tokens": 0,
        "reserved_cache_write_tokens": 0,
    }
    for changes, error in (
        ({"run_id": ""}, ValueError),
        ({"prompt": ""}, ValueError),
        ({"profile": object()}, TypeError),
        ({"context_bytes": -1}, ValueError),
    ):
        with pytest.raises(error):
            AgentRunRequest(**(common | changes))  # type: ignore[arg-type]


def test_profile_rejects_invalid_role_and_tool_collection() -> None:
    values = {
        "role": AgentRole.REVIEWER,
        "model": "model",
        "prompt_version": "v1",
        "schema_version": "v1",
        "tool_version": "v1",
        "allowed_tools": frozenset({"Read"}),
    }
    with pytest.raises(TypeError, match="AgentRole"):
        AgentProfile(**(values | {"role": "reviewer"}))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty frozenset"):
        AgentProfile(**(values | {"allowed_tools": set()}))  # type: ignore[arg-type]


def test_non_operator_request_rejects_mutating_managed_tool(tmp_path: Path) -> None:
    async def mutate(_arguments):
        return "ok"

    managed = ManagedToolGrant(
        server_name="quality",
        name="apply_patch",
        description="Apply a revision patch.",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        handler=mutate,
        effect=ToolEffect.REVISION_MUTATION,
        max_calls=1,
        timeout_ms=100,
        max_result_chars=100,
    )

    with pytest.raises(ValueError, match="operator"):
        AgentRunRequest(
            run_id="wrong-role",
            profile=reviewer_profile(model="model", prompt_version="v1"),
            prompt="review",
            output_schema={"type": "object"},
            workspace=tmp_path,
            readable_paths=(),
            editable_paths=(),
            context_bytes=1,
            estimated_input_tokens=1,
            reserved_output_tokens=1,
            reserved_cache_read_tokens=0,
            reserved_cache_write_tokens=0,
            managed_tools=(managed,),
        )


def test_usage_models_reject_invalid_values_and_keep_fallback_error() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        TokenUsage(input_tokens=-1)
    with pytest.raises(TypeError, match="TokenUsage"):
        TokenUsage().plus(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="allowed"):
        ToolCallRecord(name="Read", input={}, allowed=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="non-empty"):
        ToolCallRecord(name="Read", input={}, allowed=False, error="")
    with pytest.raises(ValueError, match="requires started_at_ms"):
        ToolCallRecord(
            name="Read", input={}, allowed=True, finished_at_ms=1,
        )
    with pytest.raises(TypeError, match="TokenUsage"):
        call_record(usage=object())
    with pytest.raises(ValueError, match="non-negative"):
        call_record(elapsed_ms=-1)
    with pytest.raises(ValueError, match="non-empty"):
        call_record(run_id="")

    assert str(AgentRunFailed(call_record())) == "Agent run failed"
