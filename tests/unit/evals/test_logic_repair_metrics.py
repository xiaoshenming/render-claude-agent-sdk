from evals._logic_repair_metrics import (
    RepairCaseMetrics,
    RoleUsageMetrics,
    summarize_repairs,
    target_lines_restored,
)

ZERO = RoleUsageMetrics(0, 0, 0, 0, 0, 0, 0, 0)


def test_target_restoration_requires_expected_line_and_removes_bad_line() -> None:
    bad = "class Demo:\n    answer = 12\n"
    original = "class Demo:\n    answer = 10\n"

    assert target_lines_restored(bad, original, original, (2,)) is True
    assert target_lines_restored(bad, bad, original, (2,)) is False


def test_summary_separates_bad_restoration_from_good_over_edit() -> None:
    cases = (
        RepairCaseMetrics(
            "bad-1",
            "known_bad",
            "needs_repair",
            True,
            "candidate_ready",
            1,
            True,
            False,
            RoleUsageMetrics(1, 80, 20, 0, 0, 2, 1, 600),
            RoleUsageMetrics(1, 10, 10, 0, 0, 1, 1, 400),
            1_000,
            None,
        ),
        RepairCaseMetrics(
            "good-1",
            "known_good",
            "needs_repair",
            True,
            "candidate_ready",
            1,
            None,
            True,
            RoleUsageMetrics(1, 40, 10, 0, 0, 1, 1, 500),
            ZERO,
            500,
            None,
        ),
        RepairCaseMetrics(
            "bad-2",
            "known_bad",
            "pass",
            False,
            "not_attempted",
            0,
            False,
            False,
            ZERO,
            ZERO,
            0,
            None,
        ),
    )

    summary = summarize_repairs(cases)

    assert summary["repair_attempted"] == 2
    assert summary["target_restored"] == 1
    assert summary["known_good_over_edit"] == 1
    assert summary["coder_usage"]["input_tokens"] == 120
    assert summary["coder_usage"]["output_tokens"] == 30
    assert summary["verifier_usage"]["total_tokens"] == 20
    assert summary["total_tokens"] == 170
