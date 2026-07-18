from manim_quality.layout.impact_policy import classify_issue


def _line_label_issue(ratio: float) -> dict:
    return {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": ratio,
        "occurrence_count": 12,
        "observed_duration": 8.0,
        "a_raw": {"class": "Text", "kind": "text", "text": "顺时针90°"},
        "b_raw": {"class": "Arrow", "kind": "shape", "text": ""},
    }


def test_short_direction_label_crossing_arrow_is_record_only() -> None:
    impact, reason = classify_issue(_line_label_issue(0.25))

    assert impact == "record_only"
    assert reason == "intentional_short_geometric_annotation"


def test_heavy_short_label_line_occlusion_remains_actionable() -> None:
    impact, reason = classify_issue(_line_label_issue(0.8))

    assert impact == "conditional_repair"
    assert reason == "persistent_label_shape_intersection"
