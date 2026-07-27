import pytest

from manim_quality.math_final.calibration import calculate_metrics


def test_calibration_metrics():
    metrics = calculate_metrics(
        {"bad": True, "miss": True, "good": False, "false_alarm": False},
        {
            "bad": "MATH_ERROR",
            "miss": "PASS",
            "good": "PASS",
            "false_alarm": "MATH_ERROR",
        },
    )
    assert metrics.true_positive == 1
    assert metrics.false_positive == 1
    assert metrics.true_negative == 1
    assert metrics.false_negative == 1
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(0.5)
    assert metrics.false_positive_rate == pytest.approx(0.5)


def test_calibration_requires_every_labeled_result():
    with pytest.raises(ValueError, match="missing verdicts"):
        calculate_metrics({"missing": True}, {})
