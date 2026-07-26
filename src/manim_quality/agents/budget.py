"""Hard pre-call and per-round Agent budget enforcement."""

from __future__ import annotations

import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass

from .usage import TokenUsage


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BudgetLimits:
    max_context_bytes: int
    max_turns: int
    max_tool_calls: int
    max_elapsed_ms: int
    max_input_tokens: int
    max_output_tokens: int
    max_cache_read_tokens: int
    max_cache_write_tokens: int
    max_total_tokens: int

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class BudgetSnapshot:
    usage: TokenUsage
    turns: int
    tool_calls: int
    elapsed_ms: int
    external_ms: int = 0
    usage_reconciled: bool = False


class BudgetTracker:
    def __init__(
        self,
        limits: BudgetLimits,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(limits, BudgetLimits):
            raise TypeError("limits must be BudgetLimits")
        self._limits = limits
        self._clock = clock
        self._started = clock()
        self._usage = TokenUsage()
        self._turns = 0
        self._tool_calls = 0
        self._external_ms = 0
        self._usage_reconciled = False

    def check_context(self, context_bytes: int) -> None:
        _require_count(context_bytes, "context_bytes")
        self.check_elapsed()
        if context_bytes > self._limits.max_context_bytes:
            raise BudgetExceeded("context bytes exceed hard limit")

    def before_round(
        self,
        *,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cache_read_tokens: int,
        reserved_cache_write_tokens: int,
    ) -> None:
        reservations = {
            "estimated_input_tokens": estimated_input_tokens,
            "reserved_output_tokens": reserved_output_tokens,
            "reserved_cache_read_tokens": reserved_cache_read_tokens,
            "reserved_cache_write_tokens": reserved_cache_write_tokens,
        }
        for name, value in reservations.items():
            _require_count(value, name)
        self.check_elapsed()
        if self._turns >= self._limits.max_turns:
            raise BudgetExceeded("turns exceed hard limit")
        self._check_round_capacity(
            estimated_input_tokens,
            reserved_output_tokens,
            reserved_cache_read_tokens,
            reserved_cache_write_tokens,
        )
        self._turns += 1

    def before_tool_call(self) -> None:
        self.check_elapsed()
        if self._tool_calls >= self._limits.max_tool_calls:
            raise BudgetExceeded("tool calls exceed hard limit")
        self._tool_calls += 1

    def record_usage(self, usage: TokenUsage) -> None:
        if not isinstance(usage, TokenUsage):
            raise TypeError("usage must be TokenUsage")
        prospective = self._usage.plus(usage)
        self._usage = prospective
        self._check_usage(prospective)

    def reconcile_usage(self, aggregate: TokenUsage) -> None:
        if not isinstance(aggregate, TokenUsage):
            raise TypeError("aggregate must be TokenUsage")
        observed = self._usage
        if (
            aggregate.input_accounted_tokens < observed.input_accounted_tokens
            or aggregate.output_tokens < observed.output_tokens
        ):
            raise ValueError("aggregate usage cannot be lower than observed usage")
        self._usage = aggregate
        self._usage_reconciled = True
        self._check_usage(aggregate)

    def check_elapsed(self) -> None:
        if self._elapsed_ms() > self._limits.max_elapsed_ms:
            raise BudgetExceeded("elapsed time exceeds hard limit")

    @contextmanager
    def external_call(self) -> Generator[None, None, None]:
        """Exclude external tool wall time from the reasoning elapsed budget."""

        started = self._clock()
        try:
            yield
        finally:
            self._external_ms += max(0, int((self._clock() - started) * 1_000))

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            usage=self._usage,
            turns=self._turns,
            tool_calls=self._tool_calls,
            elapsed_ms=self._elapsed_ms(),
            external_ms=self._external_ms,
            usage_reconciled=self._usage_reconciled,
        )

    def remaining_elapsed_ms(self) -> int:
        return max(0, self._limits.max_elapsed_ms - self._elapsed_ms())

    def _check_round_capacity(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
    ) -> None:
        checks = (
            (
                self._usage.input_tokens + input_tokens,
                self._limits.max_input_tokens,
                "input tokens",
            ),
            (
                self._usage.output_tokens + output_tokens,
                self._limits.max_output_tokens,
                "output tokens",
            ),
            (
                self._usage.cache_read_tokens + cache_read_tokens,
                self._limits.max_cache_read_tokens,
                "cache read tokens",
            ),
            (
                self._usage.cache_write_tokens + cache_write_tokens,
                self._limits.max_cache_write_tokens,
                "cache write tokens",
            ),
        )
        for actual, limit, label in checks:
            if actual > limit:
                raise BudgetExceeded(f"{label} exceed hard limit")
        reservation = (
            input_tokens + output_tokens + cache_read_tokens + cache_write_tokens
        )
        if self._usage.total_tokens + reservation > self._limits.max_total_tokens:
            raise BudgetExceeded("total tokens exceed hard limit")

    def _check_usage(self, usage: TokenUsage) -> None:
        checks = (
            (usage.input_tokens, self._limits.max_input_tokens, "input tokens"),
            (usage.output_tokens, self._limits.max_output_tokens, "output tokens"),
            (
                usage.cache_read_tokens,
                self._limits.max_cache_read_tokens,
                "cache read tokens",
            ),
            (
                usage.cache_write_tokens,
                self._limits.max_cache_write_tokens,
                "cache write tokens",
            ),
            (usage.total_tokens, self._limits.max_total_tokens, "total tokens"),
        )
        for actual, limit, label in checks:
            if actual > limit:
                raise BudgetExceeded(f"{label} exceed hard limit")

    def _elapsed_ms(self) -> int:
        wall_ms = int((self._clock() - self._started) * 1_000)
        return max(0, wall_ms - self._external_ms)


def _require_count(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value
