from app.quality_platform.retention import quality_event_record


def test_layout_issue_summary_is_retained_with_sanitized_examples() -> None:
    evidence = {
        "status": "deliver",
        "layout": {
            "status": "clean",
            "before_blocking": 0,
            "after_blocking": 0,
            "issue_summary": {
                "policy_version": "overlap-impact.v2",
                "raw_count": 2,
                "actionable_count": 1,
                "record_only_count": 1,
                "category_counts": {"text_formula_overlap": 1, "label_shape_overlap_risk": 1},
                "impact_counts": {"must_repair": 1, "record_only": 1},
                "examples": [
                    {
                        "category": "text_formula_overlap",
                        "impact": "must_repair",
                        "reason": "visible_content_intersection",
                        "scene": "Demo",
                        "event": "after_wait",
                        "time_window": {"start": 1.0, "end": 2.0},
                        "occurrence_count": 2,
                        "observed_duration": 1.0,
                        "ratio_of_smaller": 0.3,
                        "objects": [
                            {"class": "Text", "kind": "text", "text": "答案", "bbox": {"left": 0}}
                        ],
                    }
                ],
            },
        },
    }

    payload, _ = quality_event_record(evidence)
    summary = payload["layout"]["issue_summary"]

    assert summary["policy_version"] == "overlap-impact.v2"
    assert summary["category_counts"]["text_formula_overlap"] == 1
    assert summary["examples"][0]["objects"][0]["text"] == "答案"
