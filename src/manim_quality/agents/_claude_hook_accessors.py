"""Small accessors shared by Claude SDK hook state."""

from __future__ import annotations

from collections.abc import Mapping

from .usage import TokenUsage


class ClaudeHookAccessors:
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
