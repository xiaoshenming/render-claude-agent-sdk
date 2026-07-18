"""All-sample metrics for read-only Logic Reviewer shadow runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum

from manim_quality.contracts._validation import (
    require_non_empty_string,
    require_non_negative_int,
)

from .schemas import LogicDecision


class EvalTruth(StrEnum):
    KNOWN_BAD = "known_bad"
    KNOWN_GOOD = "known_good"


@dataclass(frozen=True, slots=True)
class ShadowCaseResult:
    sample_id: str
    truth: EvalTruth
    decision: LogicDecision | None
    issue_count: int
    issue_types: Sequence[str]
    expected_issue_type: str | None
    target_error_hit: bool | None
    output_corrections: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    turns: int
    observed_model_rounds: int
    elapsed_ms: int
    error: str | None

    def __post_init__(self) -> None:
        require_non_empty_string(self.sample_id, "sample_id")
        if not isinstance(self.truth, EvalTruth):
            raise TypeError("truth must be EvalTruth")
        if self.decision is not None and not isinstance(self.decision, LogicDecision):
            raise TypeError("decision must be LogicDecision or None")
        for name in (
            "issue_count",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "turns",
            "observed_model_rounds",
            "elapsed_ms",
            "output_corrections",
        ):
            require_non_negative_int(getattr(self, name), name)
        if self.error is not None:
            require_non_empty_string(self.error, "error")
        object.__setattr__(self, "issue_types", tuple(self.issue_types))
        if len(self.issue_types) != self.issue_count:
            raise ValueError("issue_types must match issue_count")
        if self.expected_issue_type is not None:
            require_non_empty_string(self.expected_issue_type, "expected_issue_type")
        if self.target_error_hit is not None and not isinstance(
            self.target_error_hit, bool
        ):
            raise TypeError("target_error_hit must be bool or None")
        if self.error is None and self.decision is None:
            raise ValueError("successful shadow case requires a decision")

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(frozen=True, slots=True)
class ShadowReport:
    attempted: int
    known_bad: int
    known_good: int
    true_positive: int
    false_negative: int
    false_positive: int
    true_negative: int
    any_issue_bad: int
    errors: int
    first_attempt_errors: int
    correction_attempted: int
    correction_recovered: int
    detection_recall: float
    detection_precision: float
    false_positive_rate: float
    bad_block_rate: float
    exact_issue_type_match_rate: float
    total_tokens: int
    average_tokens: float
    average_turns: float
    average_observed_model_rounds: float
    average_elapsed_ms: float
    repair_attempted: int
    external_verification: str
    cases: Sequence[ShadowCaseResult]

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["cases"] = [
            {
                **asdict(case),
                "truth": case.truth.value,
                "decision": case.decision.value if case.decision else None,
                "total_tokens": case.total_tokens,
            }
            for case in self.cases
        ]
        return data


def summarize_shadow(results: Sequence[ShadowCaseResult]) -> ShadowReport:
    cases = tuple(results)
    if not cases:
        raise ValueError("shadow report requires at least one attempted case")
    if not all(isinstance(case, ShadowCaseResult) for case in cases):
        raise TypeError("results must contain ShadowCaseResult values")
    known_bad = sum(case.truth is EvalTruth.KNOWN_BAD for case in cases)
    known_good = len(cases) - known_bad
    true_positive = sum(case.target_error_hit is True for case in cases)
    false_negative = known_bad - true_positive
    any_issue_bad = sum(
        case.truth is EvalTruth.KNOWN_BAD and case.issue_count > 0 for case in cases
    )
    false_positive = sum(_is_known_good_non_pass(case) for case in cases)
    true_negative = sum(
        case.truth is EvalTruth.KNOWN_GOOD
        and case.decision is LogicDecision.PASS
        and case.issue_count == 0
        and case.error is None
        for case in cases
    )
    blocked_bad = sum(_is_known_bad_blocked(case) for case in cases)
    type_matches = sum(
        case.truth is EvalTruth.KNOWN_BAD
        and case.expected_issue_type is not None
        and case.expected_issue_type in case.issue_types
        for case in cases
    )
    total_tokens = sum(case.total_tokens for case in cases)
    first_errors, correction_attempted, correction_recovered = _correction_counts(cases)
    return ShadowReport(
        attempted=len(cases),
        known_bad=known_bad,
        known_good=known_good,
        true_positive=true_positive,
        false_negative=false_negative,
        false_positive=false_positive,
        true_negative=true_negative,
        any_issue_bad=any_issue_bad,
        errors=sum(case.error is not None for case in cases),
        first_attempt_errors=first_errors,
        correction_attempted=correction_attempted,
        correction_recovered=correction_recovered,
        detection_recall=_rate(true_positive, known_bad),
        detection_precision=_rate(true_positive, any_issue_bad + false_positive),
        false_positive_rate=_rate(false_positive, known_good),
        bad_block_rate=_rate(blocked_bad, known_bad),
        exact_issue_type_match_rate=_rate(type_matches, known_bad),
        total_tokens=total_tokens,
        average_tokens=total_tokens / len(cases),
        average_turns=sum(case.turns for case in cases) / len(cases),
        average_observed_model_rounds=(
            sum(case.observed_model_rounds for case in cases) / len(cases)
        ),
        average_elapsed_ms=sum(case.elapsed_ms for case in cases) / len(cases),
        repair_attempted=0,
        external_verification="not_applicable_reviewer_shadow",
        cases=cases,
    )


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _correction_counts(cases: Sequence[ShadowCaseResult]) -> tuple[int, int, int]:
    attempted = sum(case.output_corrections > 0 for case in cases)
    recovered = sum(
        case.output_corrections > 0 and case.error is None for case in cases
    )
    first_errors = sum(
        case.error is not None or case.output_corrections > 0 for case in cases
    )
    return first_errors, attempted, recovered


def _is_known_good_non_pass(case: ShadowCaseResult) -> bool:
    return case.truth is EvalTruth.KNOWN_GOOD and (
        case.error is not None
        or case.decision is not LogicDecision.PASS
        or case.issue_count > 0
    )


def _is_known_bad_blocked(case: ShadowCaseResult) -> bool:
    return case.truth is EvalTruth.KNOWN_BAD and (
        case.error is not None
        or case.decision in (LogicDecision.NEEDS_REPAIR, LogicDecision.HUMAN_REVIEW)
    )
