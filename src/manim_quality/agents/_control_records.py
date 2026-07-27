"""Audited tool-result and structured-output records for RuntimeControls."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from ._runtime_models import (
    CorrectableOutputError,
    OutputRejected,
    RuntimeProtocolError,
)
from .usage import ToolCallRecord, recordable_tool_input


class ControlRecordMixin:
    _tool_calls: list[ToolCallRecord]
    _output_validator: object

    def _record_denied(
        self,
        name: str,
        input_data: object,
        error: Exception,
        *,
        agent_id: str | None = None,
        agent_type: str | None = None,
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
