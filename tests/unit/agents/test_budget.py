import pytest

from manim_quality.agents.budget import BudgetExceeded, BudgetLimits, BudgetTracker
from manim_quality.agents.usage import TokenUsage


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def limits(**changes: int) -> BudgetLimits:
    values = {
        "max_context_bytes": 100,
        "max_turns": 2,
        "max_tool_calls": 2,
        "max_elapsed_ms": 1_000,
        "max_input_tokens": 100,
        "max_output_tokens": 50,
        "max_cache_read_tokens": 20,
        "max_cache_write_tokens": 20,
        "max_total_tokens": 150,
    }
    values.update(changes)
    return BudgetLimits(**values)


def test_budget_checks_context_rounds_tools_and_elapsed_before_work() -> None:
    clock = Clock()
    tracker = BudgetTracker(limits(), clock=clock)

    tracker.check_context(100)
    tracker.before_round(
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    tracker.before_tool_call()
    tracker.before_tool_call()
    with pytest.raises(BudgetExceeded, match="tool calls"):
        tracker.before_tool_call()
    tracker.before_round(
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    with pytest.raises(BudgetExceeded, match="turns"):
        tracker.before_round(
            estimated_input_tokens=1,
            reserved_output_tokens=1,
            reserved_cache_read_tokens=0,
            reserved_cache_write_tokens=0,
        )
    clock.now = 2.0
    with pytest.raises(BudgetExceeded, match="elapsed"):
        tracker.check_elapsed()


def test_token_reservation_limit_is_observed_without_stopping_round() -> None:
    tracker = BudgetTracker(limits(max_total_tokens=40))
    tracker.before_round(
        estimated_input_tokens=20,
        reserved_output_tokens=10,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    tracker.record_usage(TokenUsage(input_tokens=20, output_tokens=10))

    tracker.before_round(
        estimated_input_tokens=5,
        reserved_output_tokens=6,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )

    assert "reservation:total tokens:41>40" in (
        tracker.snapshot().token_limit_observations
    )


def test_actual_usage_is_accounted_by_token_category() -> None:
    tracker = BudgetTracker(limits())
    tracker.before_round(
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    usage = TokenUsage(
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=3,
        cache_write_tokens=2,
    )

    tracker.record_usage(usage)

    assert tracker.snapshot().usage == usage
    tracker.record_usage(TokenUsage(cache_read_tokens=18))

    assert "observed:cache read tokens:21>20" in (
        tracker.snapshot().token_limit_observations
    )


def test_cache_reservation_limit_is_observed_without_stopping_round() -> None:
    tracker = BudgetTracker(limits(max_cache_read_tokens=5))

    tracker.before_round(
        estimated_input_tokens=1,
        reserved_output_tokens=1,
        reserved_cache_read_tokens=6,
        reserved_cache_write_tokens=0,
    )

    assert tracker.snapshot().turns == 1
    assert "reservation:cache read tokens:6>5" in (
        tracker.snapshot().token_limit_observations
    )


def test_budget_reconciles_authoritative_aggregate_without_adding_turn() -> None:
    tracker = BudgetTracker(limits())
    tracker.before_round(
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    tracker.record_usage(TokenUsage(input_tokens=10, output_tokens=5))

    tracker.reconcile_usage(TokenUsage(input_tokens=10, output_tokens=25))

    assert tracker.snapshot().usage == TokenUsage(input_tokens=10, output_tokens=25)
    assert tracker.snapshot().turns == 1


def test_budget_reconciles_cache_reclassified_from_input_tokens() -> None:
    tracker = BudgetTracker(limits())
    tracker.before_round(
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    tracker.record_usage(TokenUsage(input_tokens=40, output_tokens=5))

    aggregate = TokenUsage(
        input_tokens=30,
        output_tokens=8,
        cache_read_tokens=10,
    )
    tracker.reconcile_usage(aggregate)

    assert tracker.snapshot().usage == aggregate


def test_budget_keeps_observed_usage_when_aggregate_is_incomplete() -> None:
    tracker = BudgetTracker(limits())
    tracker.before_round(
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    tracker.record_usage(TokenUsage(input_tokens=10, output_tokens=5))

    tracker.reconcile_usage(TokenUsage(input_tokens=9, output_tokens=5))

    snapshot = tracker.snapshot()
    assert snapshot.usage == TokenUsage(input_tokens=10, output_tokens=5)
    assert snapshot.usage_reconciled is False


def test_external_call_time_is_excluded_from_reasoning_elapsed() -> None:
    clock = Clock()
    tracker = BudgetTracker(limits(), clock=clock)

    with tracker.external_call():
        clock.now = 100.0
    tracker.check_elapsed()
    snapshot = tracker.snapshot()

    assert snapshot.elapsed_ms == 0
    assert snapshot.external_ms == 100_000

    clock.now = 100.9
    tracker.check_elapsed()
    clock.now = 101.1
    with pytest.raises(BudgetExceeded, match="elapsed"):
        tracker.check_elapsed()


def test_snapshot_reports_whether_usage_was_reconciled() -> None:
    tracker = BudgetTracker(limits())
    tracker.before_round(
        estimated_input_tokens=10,
        reserved_output_tokens=5,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
    )
    tracker.record_usage(TokenUsage(input_tokens=10, output_tokens=5))

    assert tracker.snapshot().usage_reconciled is False
    tracker.reconcile_usage(TokenUsage(input_tokens=10, output_tokens=5))
    assert tracker.snapshot().usage_reconciled is True
