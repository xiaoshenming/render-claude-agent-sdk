from manim_quality.assurance.metrics import label_value, summarize


def test_control_group_is_a_negative_label() -> None:
    assert label_value({"human_tags": ["control"]}) is False
    assert label_value({"human_tags": ["human_bad"]}) is True


def test_summary_reports_real_confusion_metrics() -> None:
    rows = [
        sample("BAD", "human_bad", True),
        sample("GOOD", "control", True),
    ]

    result = summarize(rows)

    assert result["labeled_bad"] == 1
    assert result["deterministic_recall"] == 1.0
    assert result["deterministic_precision"] == 0.5
    assert result["deterministic_false_positive_rate"] == 1.0


def test_agent_metrics_do_not_treat_review_rate_as_recall() -> None:
    rows = [
        {**sample("BAD", "human_bad", True), "agent": {"status": "review"}},
        {**sample("GOOD", "control", True), "agent": {"status": "review"}},
    ]

    result = summarize(rows)

    assert result["agent_recall"] == 1.0
    assert result["agent_precision"] == 0.5
    assert result["agent_false_positive_rate"] == 1.0


def sample(key: str, tag: str, detected: bool) -> dict:
    return {
        "key": key,
        "human_tags": [tag],
        "expected_verdict": "",
        "detected_by_tools": detected,
        "deterministic": {},
    }
