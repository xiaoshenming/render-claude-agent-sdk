from manim_quality.logic.schemas import LogicDecision
from manim_quality.logic.shadow import EvalTruth, ShadowCaseResult, summarize_shadow


def case(
    sample_id: str,
    truth: EvalTruth,
    *,
    decision: LogicDecision | None,
    issues: int,
    error: str | None = None,
    corrections: int = 0,
) -> ShadowCaseResult:
    return ShadowCaseResult(
        sample_id=sample_id,
        truth=truth,
        decision=decision,
        issue_count=issues,
        issue_types=tuple("detected_issue" for _ in range(issues)),
        expected_issue_type=(
            "detected_issue" if truth is EvalTruth.KNOWN_BAD else None
        ),
        target_error_hit=(truth is EvalTruth.KNOWN_BAD and issues > 0),
        output_corrections=corrections,
        input_tokens=100,
        output_tokens=20,
        cache_read_tokens=10,
        cache_write_tokens=5,
        turns=2,
        observed_model_rounds=1,
        elapsed_ms=500,
        error=error,
    )


def test_shadow_metrics_keep_errors_and_all_cases_in_denominator() -> None:
    report = summarize_shadow(
        (
            case(
                "bad-hit",
                EvalTruth.KNOWN_BAD,
                decision=LogicDecision.NEEDS_REPAIR,
                issues=1,
            ),
            case(
                "bad-miss",
                EvalTruth.KNOWN_BAD,
                decision=LogicDecision.PASS,
                issues=0,
            ),
            case(
                "good-clean",
                EvalTruth.KNOWN_GOOD,
                decision=LogicDecision.PASS,
                issues=0,
            ),
            case(
                "good-error",
                EvalTruth.KNOWN_GOOD,
                decision=None,
                issues=0,
                error="SDK timeout",
            ),
        )
    )

    assert report.attempted == 4
    assert report.known_bad == 2
    assert report.known_good == 2
    assert report.true_positive == 1
    assert report.any_issue_bad == 1
    assert report.first_attempt_errors == 1
    assert report.correction_attempted == 0
    assert report.correction_recovered == 0
    assert report.false_negative == 1
    assert report.false_positive == 1
    assert report.errors == 1
    assert report.detection_recall == 0.5
    assert report.false_positive_rate == 0.5
    assert report.exact_issue_type_match_rate == 0.5
    assert "issue_type_match_rate" not in report.to_dict()
    assert report.total_tokens == 540
    assert report.average_turns == 2.0
    assert report.average_observed_model_rounds == 1.0
    assert report.repair_attempted == 0
    assert report.external_verification == "not_applicable_reviewer_shadow"


def test_shadow_counts_known_good_issue_as_false_positive() -> None:
    report = summarize_shadow(
        (
            case(
                "good-invented",
                EvalTruth.KNOWN_GOOD,
                decision=LogicDecision.RECORD_ONLY,
                issues=1,
            ),
        )
    )

    assert report.false_positive == 1
    assert report.false_positive_rate == 1.0


def test_shadow_counts_known_bad_sdk_error_as_fail_closed_block() -> None:
    report = summarize_shadow(
        (
            case(
                "bad-error",
                EvalTruth.KNOWN_BAD,
                decision=None,
                issues=0,
                error="SDK timeout",
            ),
        )
    )

    assert report.false_negative == 1
    assert report.bad_block_rate == 1.0


def test_shadow_reports_recovered_output_correction_separately() -> None:
    report = summarize_shadow(
        (
            case(
                "bad-corrected",
                EvalTruth.KNOWN_BAD,
                decision=LogicDecision.NEEDS_REPAIR,
                issues=1,
                corrections=1,
            ),
        )
    )

    assert report.first_attempt_errors == 1
    assert report.correction_attempted == 1
    assert report.correction_recovered == 1
    assert report.errors == 0


def test_shadow_does_not_treat_holds_as_clean_or_record_only_as_blocking() -> None:
    report = summarize_shadow(
        (
            case(
                "good-held",
                EvalTruth.KNOWN_GOOD,
                decision=LogicDecision.HUMAN_REVIEW,
                issues=0,
            ),
            case(
                "bad-recorded",
                EvalTruth.KNOWN_BAD,
                decision=LogicDecision.RECORD_ONLY,
                issues=1,
            ),
        )
    )

    assert report.true_negative == 0
    assert report.false_positive == 1
    assert report.false_positive_rate == 1.0
    assert report.true_positive == 1
    assert report.bad_block_rate == 0.0
