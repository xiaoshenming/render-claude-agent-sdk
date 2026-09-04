"""Stateful permission, budget, and completion controls for one Agent run."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import replace

from manim_quality.revisions.fingerprint import sha256_text

from ._control_records import ControlRecordMixin
from ._runtime_models import (
    BackendResult,
    RuntimeProtocolError,
)
from .budget import BudgetTracker
from .guards import ToolGuard
from .managed_tools import ManagedToolGrant, ToolEffect
from .usage import TokenUsage, ToolCallRecord


class RuntimeControls(ControlRecordMixin):
    def __init__(
        self,
        budget: BudgetTracker,
        guard: ToolGuard,
        *,
        output_validator: Callable[[Mapping[str, object]], None] | None = None,
        output_normalizer: (
            Callable[[Mapping[str, object]], Mapping[str, object]] | None
        ) = None,
    ) -> None:
        self._budget = budget
        self._guard = guard
        self._tool_calls: list[ToolCallRecord] = []
        self._control_token = object()
        self._round_usage_pending = True
        self._current_round_usage = TokenUsage()
        self._output_validator = output_validator
        self._output_normalizer = output_normalizer
        self._reported_turns: int | None = None
        self._observed_model_rounds: int | None = None

    @property
    def tool_calls(self) -> tuple[ToolCallRecord, ...]:
        return tuple(self._tool_calls)

    @property
    def reported_turns(self) -> int | None:
        return self._reported_turns

    @property
    def observed_model_rounds(self) -> int | None:
        return self._observed_model_rounds

    @property
    def remaining_turns(self) -> int:
        return self._budget.remaining_turns

    def before_next_round(
        self,
        *,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cache_read_tokens: int,
        reserved_cache_write_tokens: int,
    ) -> None:
        if self._round_usage_pending:
            raise RuntimeProtocolError("round usage must be recorded before next round")
        self._budget.before_round(
            estimated_input_tokens=estimated_input_tokens,
            reserved_output_tokens=reserved_output_tokens,
            reserved_cache_read_tokens=reserved_cache_read_tokens,
            reserved_cache_write_tokens=reserved_cache_write_tokens,
        )
        self._round_usage_pending = True
        self._current_round_usage = TokenUsage()

    def record_round_usage(self, usage: TokenUsage) -> None:
        if not self._round_usage_pending:
            raise RuntimeProtocolError("round usage was already recorded")
        self._budget.record_usage(usage)
        self._round_usage_pending = False
        self._current_round_usage = usage

    def merge_round_usage(self, usage: TokenUsage) -> TokenUsage:
        if self._round_usage_pending:
            raise RuntimeProtocolError("round usage must be recorded before merge")
        previous = self._current_round_usage
        merged = TokenUsage(
            input_tokens=max(previous.input_tokens, usage.input_tokens),
            output_tokens=max(previous.output_tokens, usage.output_tokens),
            cache_read_tokens=max(previous.cache_read_tokens, usage.cache_read_tokens),
            cache_write_tokens=max(
                previous.cache_write_tokens, usage.cache_write_tokens
            ),
        )
        delta = TokenUsage(
            input_tokens=merged.input_tokens - previous.input_tokens,
            output_tokens=merged.output_tokens - previous.output_tokens,
            cache_read_tokens=merged.cache_read_tokens - previous.cache_read_tokens,
            cache_write_tokens=(
                merged.cache_write_tokens - previous.cache_write_tokens
            ),
        )
        self._budget.record_usage(delta)
        self._current_round_usage = merged
        return delta

    def record_additional_usage(self, usage: TokenUsage) -> None:
        """Record usage from an isolated native subagent context."""

        self._budget.record_usage(usage)

    def authorize_tool(
        self,
        name: str,
        input_data: object,
        *,
        agent_id: str | None = None,
        agent_type: str | None = None,
        call_id: str | None = None,
    ) -> Mapping[str, object]:
        try:
            self._budget.check_tool_call()
            normalized = self._guard.authorize(
                name,
                input_data,
                agent_id=agent_id,
                agent_type=agent_type,
            )
            self._budget.record_tool_call()
        except Exception as error:
            self._record_denied(
                name,
                input_data,
                error,
                agent_id=agent_id,
                agent_type=agent_type,
                call_id=call_id,
                started_at_ms=_now_ms(),
            )
            raise
        self._tool_calls.append(
            ToolCallRecord(
                name=name,
                input=normalized,
                allowed=True,
                caller=agent_type or "parent",
                agent_id=agent_id,
                agent_type=agent_type,
                call_id=call_id,
                started_at_ms=_now_ms(),
            )
        )
        return normalized

    def authorize_output_submission(
        self, input_data: object, *, call_id: str | None = None,
    ) -> Mapping[str, object]:
        name = "StructuredOutput"
        try:
            self._budget.before_tool_call()
            normalized = self.normalize_output(input_data)
            self._validate_output(normalized)
        except Exception as error:
            self._record_denied(name, input_data, error)
            raise
        self._tool_calls.append(
            ToolCallRecord(
                name=name, input=normalized, allowed=True,
                call_id=call_id, started_at_ms=_now_ms(),
            )
        )
        return normalized

    async def execute_read_tool(self, name: str, input_data: object) -> str:
        grant = self._guard.claim_read_tool(name, input_data)
        return await self._execute_grant(name, input_data, grant)

    async def execute_managed_tool(self, name: str, input_data: object) -> str:
        grant = self._guard.claim_managed_tool(name, input_data)
        return await self._execute_grant(name, input_data, grant)

    async def execute_managed_tool_content(
        self, name: str, input_data: object
    ) -> tuple[Mapping[str, object], ...]:
        grant = self._guard.claim_managed_tool(name, input_data)
        return await self._execute_grant_content(name, input_data, grant)

    async def _execute_grant(self, name: str, input_data: object, grant) -> str:
        result = await self._execute_grant_result(name, input_data, grant)
        return result.text

    async def _execute_grant_content(
        self, name: str, input_data: object, grant
    ) -> tuple[Mapping[str, object], ...]:
        result = await self._execute_grant_result(name, input_data, grant)
        return result.content

    async def _execute_grant_result(self, name: str, input_data: object, grant):
        normalized = grant.normalize_input(input_data)
        try:
            with self._budget.external_call():
                result = await grant.execute(normalized)
        except Exception as error:
            if (
                isinstance(grant, ManagedToolGrant)
                and grant.effect is not ToolEffect.READ_ONLY
            ):
                self._guard.refund_parent_managed_tool(name)
            error_fingerprint = f"{type(error).__name__}:{str(error)[:1_000]}"
            self._record_tool_result(
                name,
                normalized,
                status="error",
                result_hash=sha256_text(error_fingerprint),
                error=error_fingerprint[:500],
            )
            raise
        self._record_tool_result(
            name,
            normalized,
            status=result.status,
            result_hash=result.result_hash,
        )
        return result

    def record_output_correction(self, error_text: str) -> None:
        self._tool_calls.append(
            ToolCallRecord(
                name="StructuredOutputCorrection",
                input={"reason": error_text[:1_000]},
                allowed=True,
            )
        )

    def finish_tool_timing(self, call_id: str) -> None:
        """Record one SDK tool wall time without changing its result semantics."""
        finished = _now_ms()
        for index in range(len(self._tool_calls) - 1, -1, -1):
            record = self._tool_calls[index]
            if record.call_id != call_id or record.finished_at_ms is not None:
                continue
            started = record.started_at_ms or finished
            self._tool_calls[index] = replace(
                record,
                finished_at_ms=finished,
                duration_ms=max(0, finished - started),
            )
            return

    def reconcile_usage(self, aggregate: TokenUsage) -> None:
        if self._round_usage_pending:
            raise RuntimeProtocolError("round usage must be recorded before reconcile")
        self._budget.reconcile_usage(aggregate)

    def record_reported_turns(self, turns: int) -> None:
        if isinstance(turns, bool) or not isinstance(turns, int) or turns < 0:
            raise RuntimeProtocolError("reported turns must be a non-negative integer")
        self._reported_turns = turns

    def record_observed_model_rounds(self, turns: int) -> None:
        if isinstance(turns, bool) or not isinstance(turns, int) or turns < 0:
            raise RuntimeProtocolError("observed rounds must be a non-negative integer")
        self._observed_model_rounds = turns

    def complete(self, structured_output: Mapping[str, object]) -> BackendResult:
        if self._round_usage_pending:
            raise RuntimeProtocolError("round usage must be recorded before completion")
        if any(
            call.allowed
            and call.name.startswith("mcp__")
            and call.result_status is None
            for call in self._tool_calls
        ):
            raise RuntimeProtocolError(
                "authorized read tool was not executed and audited"
            )
        normalized = self.normalize_output(structured_output)
        self._validate_output(normalized)
        return BackendResult(
            structured_output=normalized,
            _control_token=self._control_token,
        )

    def require_managed_result(self, result: BackendResult) -> None:
        if (
            not isinstance(result, BackendResult)
            or result._control_token is not self._control_token
        ):
            raise RuntimeProtocolError(
                "backend result was not finalized through runtime controls"
            )

def _now_ms() -> int:
    return time.time_ns() // 1_000_000
