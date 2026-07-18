"""Stateful permission, budget, and completion controls for one Agent run."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace

from manim_quality.contracts._json_values import freeze_json_object
from manim_quality.revisions.fingerprint import sha256_text

from ._runtime_models import (
    BackendResult,
    CorrectableOutputError,
    OutputRejected,
    RuntimeProtocolError,
)
from .budget import BudgetTracker
from .guards import ToolGuard
from .usage import TokenUsage, ToolCallRecord, recordable_tool_input


class RuntimeControls:
    def __init__(
        self,
        budget: BudgetTracker,
        guard: ToolGuard,
        *,
        output_validator: Callable[[Mapping[str, object]], None] | None = None,
    ) -> None:
        self._budget = budget
        self._guard = guard
        self._tool_calls: list[ToolCallRecord] = []
        self._control_token = object()
        self._round_usage_pending = True
        self._current_round_usage = TokenUsage()
        self._output_validator = output_validator
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

    def authorize_tool(self, name: str, input_data: object) -> Mapping[str, object]:
        try:
            self._budget.before_tool_call()
            normalized = self._guard.authorize(name, input_data)
        except Exception as error:
            self._record_denied(name, input_data, error)
            raise
        self._tool_calls.append(
            ToolCallRecord(name=name, input=normalized, allowed=True)
        )
        return normalized

    def authorize_output_submission(self, input_data: object) -> Mapping[str, object]:
        name = "StructuredOutput"
        try:
            self._budget.before_tool_call()
            normalized = freeze_json_object(input_data, "structured_output")
            self._validate_output(normalized)
        except Exception as error:
            self._record_denied(name, input_data, error)
            raise
        self._tool_calls.append(
            ToolCallRecord(name=name, input=normalized, allowed=True)
        )
        return normalized

    async def execute_read_tool(self, name: str, input_data: object) -> str:
        grant = self._guard.claim_read_tool(name, input_data)
        normalized = grant.normalize_input(input_data)
        try:
            result = await grant.execute(normalized)
        except Exception as error:
            error_fingerprint = f"{type(error).__name__}:{str(error)[:1_000]}"
            self._record_tool_result(
                name,
                normalized,
                status="error",
                result_hash=sha256_text(error_fingerprint),
            )
            raise
        self._record_tool_result(
            name,
            normalized,
            status=result.status,
            result_hash=result.result_hash,
        )
        return result.text

    def record_output_correction(self, error_text: str) -> None:
        self._tool_calls.append(
            ToolCallRecord(
                name="StructuredOutputCorrection",
                input={"reason": error_text[:1_000]},
                allowed=True,
            )
        )

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
        normalized = freeze_json_object(structured_output, "structured_output")
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

    def _record_denied(self, name: str, input_data: object, error: Exception) -> None:
        self._tool_calls.append(
            ToolCallRecord(
                name=name,
                input=recordable_tool_input(input_data),
                allowed=False,
                error=str(error),
            )
        )

    def _record_tool_result(
        self,
        name: str,
        input_data: Mapping[str, object],
        *,
        status: str,
        result_hash: str,
    ) -> None:
        for index in range(len(self._tool_calls) - 1, -1, -1):
            record = self._tool_calls[index]
            if (
                record.name == name
                and record.allowed
                and record.result_status is None
                and record.input == input_data
            ):
                self._tool_calls[index] = replace(
                    record,
                    result_status=status,
                    result_hash=result_hash,
                )
                return
        raise RuntimeProtocolError("read tool result has no authorized call record")

    def _validate_output(self, output: Mapping[str, object]) -> None:
        if self._output_validator is None:
            return
        try:
            self._output_validator(output)
        except CorrectableOutputError as error:
            raise OutputRejected(str(error)) from error
