"""Small accessors shared by Claude SDK hook state."""

from __future__ import annotations

from collections.abc import Mapping

from .usage import TokenUsage


class ClaudeHookAccessors:
    _controls: object
    _usage: TokenUsage
    _turns: int
    _sdk_messages: list[dict[str, object]]
    _subagents: object

    @property
    def usage(self) -> TokenUsage:
        return self._usage

    @property
    def turns(self) -> int:
        return self._turns

    @property
    def sdk_turn_floor(self) -> int:
        return self._turns

    @property
    def sdk_messages(self) -> tuple[Mapping[str, object], ...]:
        return tuple(self._sdk_messages)

    @property
    def subagent_results(self) -> tuple[Mapping[str, object], ...]:
        return self._subagents.results  # type: ignore[attr-defined]

    @property
    def required_subagent_names(self) -> frozenset[str]:
        return self._subagents.expected_names  # type: ignore[attr-defined]

    def validate_subagent_protocol(self) -> None:
        self._subagents.validate_complete()  # type: ignore[attr-defined]

    def raise_failure(self) -> None:
        failure = getattr(self, "_failure", None)
        if failure is not None:
            raise failure

    async def execute_read_tool(self, name: str, input_data: object) -> str:
        return await self._controls.execute_read_tool(name, input_data)  # type: ignore[attr-defined]

    async def execute_managed_tool(self, name: str, input_data: object) -> str:
        return await self._controls.execute_managed_tool(name, input_data)  # type: ignore[attr-defined]

    async def execute_managed_tool_content(
        self, name: str, input_data: object
    ) -> tuple[Mapping[str, object], ...]:
        return await self._controls.execute_managed_tool_content(  # type: ignore[attr-defined]
            name, input_data
        )
