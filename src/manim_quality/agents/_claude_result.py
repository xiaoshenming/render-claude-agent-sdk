"""Terminal Claude SDK result validation and usage reconciliation."""

from __future__ import annotations

from collections.abc import Mapping

from claude_agent_sdk import ResultMessage

from ._claude_hook_values import ClaudeSdkProtocolError, parse_token_usage
from .usage import TokenUsage


class ClaudeSdkRunError(RuntimeError):
    pass


def result_tree_usage(
    result: ResultMessage,
    observed_usage: TokenUsage,
) -> TokenUsage:
    """Return the strongest aggregate without losing observed partial usage."""

    model_usage = _model_usage(result.model_usage)
    if model_usage.total_tokens:
        return model_usage
    reported = parse_token_usage(result.usage)
    if _dominates(reported, observed_usage):
        return reported
    return TokenUsage(
        input_tokens=max(reported.input_tokens, observed_usage.input_tokens),
        output_tokens=max(reported.output_tokens, observed_usage.output_tokens),
        cache_read_tokens=max(
            reported.cache_read_tokens,
            observed_usage.cache_read_tokens,
        ),
        cache_write_tokens=max(
            reported.cache_write_tokens,
            observed_usage.cache_write_tokens,
        ),
    )


def _dominates(aggregate: TokenUsage, observed: TokenUsage) -> bool:
    return (
        aggregate.input_accounted_tokens >= observed.input_accounted_tokens
        and aggregate.output_tokens >= observed.output_tokens
    )


def validate_terminal_result(
    result: ResultMessage,
    *,
    minimum_turns: int,
    validate_subagents,
) -> None:
    """Validate terminal semantics after usage has already been persisted."""

    if result.is_error:
        details = "; ".join(result.errors or []) or result.subtype
        raise ClaudeSdkRunError(f"Claude Agent SDK failed: {details}")
    if result.num_turns < minimum_turns:
        raise ClaudeSdkProtocolError(
            "SDK turn count mismatch: "
            f"result={result.num_turns}, minimum_sdk_turns={minimum_turns}"
        )
    validate_subagents()


def _model_usage(value: object) -> TokenUsage:
    if value is None:
        return TokenUsage()
    if not isinstance(value, Mapping):
        raise ClaudeSdkProtocolError("SDK model_usage must be a mapping")
    total = TokenUsage()
    for model, raw_usage in value.items():
        if not isinstance(model, str) or not isinstance(raw_usage, Mapping):
            raise ClaudeSdkProtocolError("invalid SDK model_usage entry")
        total = total.plus(TokenUsage(
            input_tokens=_count(raw_usage, "inputTokens"),
            output_tokens=_count(raw_usage, "outputTokens"),
            cache_read_tokens=_count(raw_usage, "cacheReadInputTokens"),
            cache_write_tokens=_count(raw_usage, "cacheCreationInputTokens"),
        ))
    return total


def _count(value: Mapping[object, object], key: str) -> int:
    count = value.get(key, 0)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ClaudeSdkProtocolError(f"invalid SDK model_usage field: {key}")
    return count
