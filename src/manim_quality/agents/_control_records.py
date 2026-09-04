"""Audited tool-result and structured-output records for RuntimeControls."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import replace

from manim_quality.contracts._json_values import freeze_json_object

from ._runtime_models import (
    CorrectableOutputError,
    OutputRejected,
    RuntimeProtocolError,
)
from .usage import ToolCallRecord, recordable_tool_input


class ControlRecordMixin:
    _tool_calls: list[ToolCallRecord]
    _output_validator: object
    _output_normalizer: Callable[[Mapping[str, object]], Mapping[str, object]] | None

    def normalize_output(self, value: Mapping[str, object]) -> Mapping[str, object]:
        """Apply the caller's evidence projection at every output boundary."""
        normalized = freeze_json_object(value, "structured_output")
        if self._output_normalizer is not None:
            normalized = freeze_json_object(
                self._output_normalizer(normalized), "structured_output")
        return normalized

    def _record_denied(
        self,
        name: str,
        input_data: object,
        error: Exception,
        *,
        agent_id: str | None = None,
        agent_type: str | None = None,
        call_id: str | None = None,
        started_at_ms: int | None = None,
    ) -> None:
        self._tool_calls.append(
            ToolCallRecord(
                name=name,
                input=recordable_tool_input(input_data),
                allowed=False,
                error=str(error),
                caller=agent_type or "parent",
                agent_id=agent_id,
                agent_type=agent_type,
                call_id=call_id,
                started_at_ms=started_at_ms,
                finished_at_ms=started_at_ms,
                duration_ms=0 if started_at_ms is not None else None,
            )
        )

    def _record_tool_result(
        self,
        name: str,
        input_data: Mapping[str, object],
        *,
        status: str,
        result_hash: str,
        error: str | None = None,
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
                    error=error,
                    finished_at_ms=(finished := time.time_ns() // 1_000_000),
                    duration_ms=max(
                        0, finished - (record.started_at_ms or finished)),
                )
                return
        raise RuntimeProtocolError("read tool result has no authorized call record")

    def _validate_output(self, output: Mapping[str, object]) -> None:
        if self._output_validator is None:
            return
        try:
            self._output_validator(output)  # type: ignore[operator]
        except CorrectableOutputError as error:
            raise OutputRejected(str(error)) from error
