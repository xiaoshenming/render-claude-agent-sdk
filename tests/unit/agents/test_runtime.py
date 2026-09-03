from dataclasses import replace
from pathlib import Path

import anyio
import pytest

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.read_tools import ReadonlyToolGrant
from manim_quality.agents.runtime import (
    AgentBackend,
    AgentRunFailed,
    AgentRunRequest,
    AgentRuntime,
    BackendRequest,
    BackendResult,
    RuntimeControls,
)
from manim_quality.agents.tool_policy import ToolInputPolicy
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class FakeBackend(AgentBackend):
    def __init__(
        self,
        *,
        fail: bool = False,
        second_round: bool = False,
        tool: str = "Read",
        extra_tool: bool = False,
    ) -> None:
        self.fail = fail
        self.second_round = second_round
        self.tool = tool
        self.extra_tool = extra_tool
        self.calls = 0

    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        self.calls += 1
        controls.record_round_usage(
            TokenUsage(
                input_tokens=8,
                output_tokens=3,
                cache_read_tokens=2,
                cache_write_tokens=1,
            )
        )
        controls.authorize_tool(self.tool, {"file_path": request.readable_paths[0]})
        if self.extra_tool:
            controls.authorize_tool(
                "Read", {"file_path": request.readable_paths[0], "offset": 2}
            )
        if self.second_round:
            controls.before_next_round(
                estimated_input_tokens=8,
                reserved_output_tokens=3,
                reserved_cache_read_tokens=2,
                reserved_cache_write_tokens=1,
            )
            controls.record_round_usage(TokenUsage(input_tokens=8, output_tokens=3))
        if self.fail:
            raise RuntimeError("backend failed")
        return controls.complete({"decision": "PASS"})


class UnmanagedBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        return BackendResult(structured_output={"decision": "PASS"})


class MissingUsageBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        return controls.complete({"decision": "PASS"})


class OverBudgetBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        controls.record_round_usage(TokenUsage(input_tokens=101))
        return controls.complete({"decision": "PASS"})


class DuplicateReadThenUniqueBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        controls.record_round_usage(TokenUsage(input_tokens=1))
        payload = {"file_path": request.readable_paths[0]}
        controls.authorize_tool("Read", payload)
        try:
            controls.authorize_tool("Read", payload)
        except Exception:
            pass
        controls.authorize_tool("Read", {**payload, "offset": 2})
        return controls.complete({"decision": "PASS"})


class IncompleteAggregateBackend(AgentBackend):
    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        controls.record_round_usage(TokenUsage(input_tokens=10, output_tokens=5))
        controls.reconcile_usage(TokenUsage(input_tokens=9, output_tokens=5))
        return controls.complete({"decision": "PASS"})


def budget(**changes: int) -> BudgetLimits:
    values = {
        "max_context_bytes": 1_000,
        "max_turns": 2,
        "max_tool_calls": 2,
        "max_elapsed_ms": 5_000,
        "max_input_tokens": 100,
        "max_output_tokens": 50,
        "max_cache_read_tokens": 20,
        "max_cache_write_tokens": 20,
        "max_total_tokens": 150,
    }
    values.update(changes)
    return BudgetLimits(**values)


def request(workspace: Path, candidate: Path) -> AgentRunRequest:
    return AgentRunRequest(
        run_id="run-1",
        profile=reviewer_profile(model="fake-model", prompt_version="review-v1"),
        prompt="Review the candidate.",
        output_schema={"type": "object", "required": ["decision"]},
        workspace=workspace,
        readable_paths=(candidate,),
        editable_paths=(),
        context_bytes=100,
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=2,
        reserved_cache_write_tokens=1,
    )


def _inspect(arguments):
    return f"truth={arguments['truth']}"


def read_tool() -> ReadonlyToolGrant:
    return ReadonlyToolGrant(
        server_name="geometry",
        name="inspect_relation",
        description="Inspect one relation.",
        input_schema={
            "type": "object",
            "properties": {"truth": {"type": "boolean"}},
            "required": ["truth"],
            "additionalProperties": False,
        },
        handler=_inspect,
        max_calls=1,
        timeout_ms=100,
        max_result_chars=100,
    )


def test_runtime_returns_candidate_and_persists_complete_usage(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(FakeBackend(), sink, budget())

    result = runtime.run(request(tmp_path, candidate))

    assert result.structured_output == {"decision": "PASS"}
    assert result.record == sink.records[0]
    assert result.record.usage == TokenUsage(
        input_tokens=8,
        output_tokens=3,
        cache_read_tokens=2,
        cache_write_tokens=1,
    )
    assert result.record.model == "fake-model"
    assert result.record.prompt == "Review the candidate."
    assert result.record.prompt_version == "review-v1"
    assert result.record.schema_version
    assert result.record.tool_version
    assert len(result.record.tool_calls) == 1
    assert result.record.turns == 1
    assert result.record.error is None


def test_runtime_keeps_output_when_terminal_usage_is_incomplete(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()

    result = AgentRuntime(
        IncompleteAggregateBackend(), sink, budget()
    ).run(request(tmp_path, candidate))

    assert result.structured_output == {"decision": "PASS"}
    assert result.record.error is None
    assert result.record.usage == TokenUsage(input_tokens=10, output_tokens=5)
    assert result.record.usage_complete is False


def test_runtime_does_not_classify_validator_bug_as_correctable_output(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    def broken_validator(_value) -> None:
        raise RuntimeError("validator implementation failed")

    run_request = replace(
        request(tmp_path, candidate), output_validator=broken_validator
    )

    with pytest.raises(
        AgentRunFailed, match="validator implementation failed"
    ) as error:
        AgentRuntime(FakeBackend(), MemorySink(), budget()).run(run_request)

    assert "OutputRejected" not in (error.value.record.error or "")


def test_runtime_records_actual_successful_round_count(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    result = AgentRuntime(FakeBackend(second_round=True), MemorySink(), budget()).run(
        request(tmp_path, candidate)
    )

    assert result.record.turns == 2
    assert result.record.usage.input_tokens == 16


def test_runtime_passes_exact_tools_and_remaining_deadline_to_backend(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    class CapturingBackend(FakeBackend):
        last_request: BackendRequest | None = None

        def run(
            self, request: BackendRequest, controls: RuntimeControls
        ) -> BackendResult:
            self.last_request = request
            return super().run(request, controls)

    backend = CapturingBackend()
    AgentRuntime(backend, MemorySink(), budget()).run(request(tmp_path, candidate))

    assert backend.last_request is not None
    assert backend.last_request.allowed_tools == ("Read",)
    assert backend.last_request.output_schema == {
        "type": "object",
        "required": ("decision",),
    }
    assert backend.last_request.max_turns == 2
    assert backend.last_request.max_tool_calls == 2
    assert backend.last_request.estimated_input_tokens == 10
    assert backend.last_request.reserved_output_tokens == 5
    assert backend.last_request.reserved_cache_read_tokens == 2
    assert backend.last_request.reserved_cache_write_tokens == 1
    assert 0 < backend.last_request.timeout_ms <= 5_000


def test_runtime_passes_explicit_read_tool_grants_separately_from_profile(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")

    class CapturingBackend(FakeBackend):
        last_request: BackendRequest | None = None

        def run(
            self, request: BackendRequest, controls: RuntimeControls
        ) -> BackendResult:
            self.last_request = request
            return super().run(request, controls)

    backend = CapturingBackend()
    tool = read_tool()
    run_request = replace(request(tmp_path, candidate), read_tools=(tool,))

    AgentRuntime(backend, MemorySink(), budget()).run(run_request)

    assert backend.last_request is not None
    assert backend.last_request.allowed_tools == ("Read",)
    assert backend.last_request.read_tools == (tool,)


def test_runtime_records_bounded_read_tool_result_hash(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = read_tool()

    class ReadToolBackend(AgentBackend):
        def run(
            self, request: BackendRequest, controls: RuntimeControls
        ) -> BackendResult:
            controls.record_round_usage(TokenUsage(input_tokens=1, output_tokens=1))
            arguments = {"truth": True}
            controls.authorize_tool(tool.sdk_name, arguments)
            result = anyio.run(controls.execute_read_tool, tool.sdk_name, arguments)
            assert result == "truth=True"
            return controls.complete({"decision": "PASS"})

    outcome = AgentRuntime(ReadToolBackend(), MemorySink(), budget()).run(
        replace(request(tmp_path, candidate), read_tools=(tool,))
    )

    call = outcome.record.tool_calls[0]
    assert call.name == tool.sdk_name
    assert call.result_status == "ok"
    assert call.result_hash is not None and call.result_hash.startswith("sha256:")


def test_runtime_enforces_per_run_builtin_tool_policy(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    run_request = replace(
        request(tmp_path, candidate),
        tool_policies={"Read": ToolInputPolicy(max_calls=1)},
    )

    with pytest.raises(AgentRunFailed, match="call limit"):
        AgentRuntime(FakeBackend(extra_tool=True), MemorySink(), budget()).run(
            run_request
        )


def test_runtime_rejects_unexecuted_authorized_read_tool(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = read_tool()

    class IncompleteReadToolBackend(AgentBackend):
        def run(
            self, request: BackendRequest, controls: RuntimeControls
        ) -> BackendResult:
            controls.record_round_usage(TokenUsage(input_tokens=1, output_tokens=1))
            controls.authorize_tool(tool.sdk_name, {"truth": True})
            return controls.complete({"decision": "PASS"})

    with pytest.raises(AgentRunFailed, match="not executed"):
        AgentRuntime(IncompleteReadToolBackend(), MemorySink(), budget()).run(
            replace(request(tmp_path, candidate), read_tools=(tool,))
        )


def test_runtime_counts_read_tool_definition_in_context_budget(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    tool = replace(read_tool(), description="x" * 2_000)

    with pytest.raises(AgentRunFailed, match="context bytes"):
        AgentRuntime(FakeBackend(), MemorySink(), budget(max_context_bytes=500)).run(
            replace(
                request(tmp_path, candidate),
                context_bytes=100,
                read_tools=(tool,),
            )
        )


def test_runtime_persists_failure_without_certifying_it(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(FakeBackend(fail=True), sink, budget())

    with pytest.raises(AgentRunFailed, match="backend failed") as captured:
        runtime.run(request(tmp_path, candidate))

    assert captured.value.record == sink.records[0]
    assert "backend failed" in sink.records[0].error
    assert not hasattr(sink.records[0], "accepted")


def test_runtime_records_denied_tool_attempt(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(FakeBackend(tool="Bash"), sink, budget())

    with pytest.raises(AgentRunFailed, match="not allowed"):
        runtime.run(request(tmp_path, candidate))

    assert sink.records[0].tool_calls[0].name == "Bash"
    assert sink.records[0].tool_calls[0].allowed is False


def test_runtime_enforces_next_round_budget_inside_backend(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(FakeBackend(second_round=True), sink, budget(max_turns=1))

    with pytest.raises(AgentRunFailed, match="turns"):
        runtime.run(request(tmp_path, candidate))
    assert sink.records[0].error is not None


def test_runtime_fails_before_backend_when_initial_budget_cannot_fit(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    backend = FakeBackend()
    runtime = AgentRuntime(backend, sink, budget(max_context_bytes=10))

    with pytest.raises(AgentRunFailed, match="context bytes"):
        runtime.run(request(tmp_path, candidate))

    assert backend.calls == 0
    assert "BudgetExceeded" in sink.records[0].error


def test_runtime_rejects_backend_result_not_finalized_by_controls(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(UnmanagedBackend(), sink, budget())

    with pytest.raises(AgentRunFailed, match="runtime controls"):
        runtime.run(request(tmp_path, candidate))


def test_runtime_requires_usage_for_every_completed_round(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(MissingUsageBackend(), sink, budget())

    with pytest.raises(AgentRunFailed, match="round usage"):
        runtime.run(request(tmp_path, candidate))


def test_runtime_keeps_running_and_audits_usage_when_token_limit_is_exceeded(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(OverBudgetBackend(), sink, budget())

    result = runtime.run(request(tmp_path, candidate))

    assert sink.records[0].usage.input_tokens == 101
    assert result.record.error is None
    assert "observed:input tokens:101>100" in (
        result.record.token_limit_observations
    )


def test_tool_budget_rejection_is_included_in_audit(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(FakeBackend(extra_tool=True), sink, budget(max_tool_calls=1))

    with pytest.raises(AgentRunFailed, match="tool calls"):
        runtime.run(request(tmp_path, candidate))

    assert len(sink.records[0].tool_calls) == 2
    assert sink.records[0].tool_calls[1].allowed is False
    assert "tool calls" in sink.records[0].tool_calls[1].error


def test_denied_duplicate_read_does_not_consume_tool_budget(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate.py"
    candidate.write_text("pass\n", encoding="utf-8")
    sink = MemorySink()
    runtime = AgentRuntime(
        DuplicateReadThenUniqueBackend(), sink, budget(max_tool_calls=2))

    runtime.run(request(tmp_path, candidate))

    assert [call.allowed for call in sink.records[0].tool_calls] == [
        True, False, True,
    ]
    assert sink.records[0].error is None
