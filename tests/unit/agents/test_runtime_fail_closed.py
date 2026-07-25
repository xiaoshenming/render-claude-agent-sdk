from pathlib import Path

import pytest

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import (
    AgentBackend,
    AgentRunFailed,
    AgentRunRequest,
    AgentRuntime,
    BackendRequest,
    BackendResult,
    RuntimeControls,
)
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class PrematureRoundBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        controls.before_next_round(
            estimated_input_tokens=1,
            reserved_output_tokens=1,
            reserved_cache_read_tokens=0,
            reserved_cache_write_tokens=0,
        )
        raise AssertionError("unreachable")


class DuplicateUsageBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        controls.record_round_usage(TokenUsage(input_tokens=1))
        controls.record_round_usage(TokenUsage(input_tokens=1))
        raise AssertionError("unreachable")


class InvalidToolInputBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        controls.record_round_usage(TokenUsage(input_tokens=1))
        controls.authorize_tool("Read", {"file_path": object()})
        raise AssertionError("unreachable")


class WrongResultBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        controls.record_round_usage(TokenUsage(input_tokens=1))
        return object()  # type: ignore[return-value]


def budget() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=1_000,
        max_turns=2,
        max_tool_calls=2,
        max_elapsed_ms=5_000,
        max_input_tokens=100,
        max_output_tokens=50,
        max_cache_read_tokens=20,
        max_cache_write_tokens=20,
        max_total_tokens=150,
    )


def request(workspace: Path, readable: Path) -> AgentRunRequest:
    return AgentRunRequest(
        run_id="run-1",
        profile=reviewer_profile(model="model", prompt_version="v1"),
        prompt="review",
        output_schema={"type": "object"},
        workspace=workspace,
        readable_paths=(readable,),
        editable_paths=(),
        context_bytes=10,
        estimated_input_tokens=5,
        reserved_output_tokens=2,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )


@pytest.mark.parametrize(
    ("backend", "message"),
    [
        (PrematureRoundBackend(), "before next round"),
        (DuplicateUsageBackend(), "already recorded"),
        (WrongResultBackend(), "runtime controls"),
    ],
)
def test_runtime_rejects_backend_protocol_violations(
    tmp_path: Path, backend: AgentBackend, message: str
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()

    with pytest.raises(AgentRunFailed, match=message):
        AgentRuntime(backend, sink, budget()).run(request(tmp_path, candidate))

    assert sink.records[0].error is not None


def test_runtime_audits_unrecordable_denied_tool_input(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()

    with pytest.raises(AgentRunFailed):
        AgentRuntime(InvalidToolInputBackend(), sink, budget()).run(
            request(tmp_path, candidate)
        )

    assert sink.records[0].tool_calls[0].input == {"unrecordable_input_type": "dict"}


def test_runtime_audits_guard_setup_failure(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    sink = MemorySink()

    with pytest.raises(AgentRunFailed, match="declared path"):
        AgentRuntime(PrematureRoundBackend(), sink, budget()).run(
            request(tmp_path, missing)
        )

    assert len(sink.records) == 1
    assert sink.records[0].tool_calls == ()


def test_runtime_rejects_invalid_runtime_dependencies_and_request() -> None:
    sink = MemorySink()
    with pytest.raises(TypeError, match="AgentBackend"):
        AgentRuntime(object(), sink, budget())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="UsageSink"):
        AgentRuntime(PrematureRoundBackend(), object(), budget())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="AgentRunRequest"):
        AgentRuntime(PrematureRoundBackend(), sink, budget()).run(object())  # type: ignore[arg-type]
