"""Controlled runtime boundary around an SDK Agent backend."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Protocol, runtime_checkable

from manim_quality.contracts._json_values import freeze_json_object

from ._backend_request import build_backend_request
from ._controls import RuntimeControls
from ._runtime_models import (
    AgentRunFailed,
    AgentRunRequest,
    AgentRunResult,
    BackendRequest,
    BackendResult,
)
from .budget import BudgetLimits, BudgetTracker
from .guards import ToolGuard
from .usage import UsageSink, build_agent_call_record


@runtime_checkable
class AgentBackend(Protocol):
    def run(
        self, request: BackendRequest, controls: RuntimeControls
    ) -> BackendResult: ...


class AgentRuntime:
    def __init__(
        self,
        backend: AgentBackend,
        usage_sink: UsageSink,
        limits: BudgetLimits,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(backend, AgentBackend):
            raise TypeError("backend must implement AgentBackend")
        if not isinstance(usage_sink, UsageSink):
            raise TypeError("usage_sink must implement UsageSink")
        self._backend = backend
        self._usage_sink = usage_sink
        self._limits = limits
        self._clock = clock

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        if not isinstance(request, AgentRunRequest):
            raise TypeError("request must be AgentRunRequest")
        budget = BudgetTracker(self._limits, clock=self._clock)
        controls: RuntimeControls | None = None
        output: Mapping[str, object] | None = None
        error_text: str | None = None
        caught: Exception | None = None
        try:
            guard = _build_guard(request)
            controls = RuntimeControls(
                budget, guard, output_validator=request.output_validator,
                output_normalizer=request.output_normalizer,
            )
            _reserve_initial_context(request, budget)
            backend_request = build_backend_request(
                request,
                guard=guard,
                budget=budget,
                limits=self._limits,
            )
            backend_result = self._backend.run(backend_request, controls)
            controls.require_managed_result(backend_result)
            output = backend_result.structured_output
            budget.check_elapsed()
        except Exception as error:
            caught = error
            error_text = f"{type(error).__name__}: {error}"
        snapshot = budget.snapshot()
        tool_calls = controls.tool_calls if controls is not None else ()
        turns, observed_rounds = _round_counts(controls, snapshot.turns)
        record = build_agent_call_record(
            request=request,
            output=output,
            tool_calls=tool_calls,
            usage=snapshot.usage,
            turns=turns,
            observed_model_rounds=observed_rounds,
            elapsed_ms=snapshot.elapsed_ms,
            error=error_text,
            external_tool_ms=snapshot.external_ms,
            usage_complete=snapshot.usage_reconciled,
            token_limit_observations=snapshot.token_limit_observations,
        )
        self._usage_sink.save(record)
        if caught is not None:
            _raise_run_failed(record, caught)
        structured_output = record.structured_output or freeze_json_object(
            {}, "structured_output"
        )
        return AgentRunResult(
            structured_output=structured_output,
            record=record,
            sdk_messages=backend_result.sdk_messages,
            subagent_results=backend_result.subagent_results,
        )


def _reserve_initial_context(request, budget) -> None:
    budget.check_context(_request_context_bytes(request))
    budget.before_round(
        estimated_input_tokens=request.estimated_input_tokens,
        reserved_output_tokens=request.reserved_output_tokens,
        reserved_cache_read_tokens=request.reserved_cache_read_tokens,
        reserved_cache_write_tokens=request.reserved_cache_write_tokens,
    )


def _raise_run_failed(record, caught: Exception) -> None:
    raise AgentRunFailed(
        record,
        sdk_messages=getattr(caught, "sdk_messages", ()),
        subagent_results=getattr(caught, "subagent_results", ()),
    ) from caught


def _round_counts(
    controls: RuntimeControls | None, reserved_rounds: int
) -> tuple[int, int]:
    if controls is None:
        return reserved_rounds, reserved_rounds
    observed = controls.observed_model_rounds
    observed = observed if observed is not None else reserved_rounds
    reported = controls.reported_turns
    return (reported if reported is not None else observed), observed


def _request_context_bytes(request: AgentRunRequest) -> int:
    tools = (*request.read_tools, *request.managed_tools)
    tool_bytes = sum(item.context_bytes for item in tools)
    subagent_bytes = sum(item.context_bytes for item in request.subagents)
    return request.context_bytes + tool_bytes + subagent_bytes


def _build_guard(request: AgentRunRequest) -> ToolGuard:
    return ToolGuard(
        workspace=request.workspace,
        profile=request.profile,
        readable_paths=request.readable_paths,
        editable_paths=request.editable_paths,
        read_tools=request.read_tools,
        managed_tools=request.managed_tools,
        tool_policies=request.tool_policies,
        subagents=request.subagents,
    )
