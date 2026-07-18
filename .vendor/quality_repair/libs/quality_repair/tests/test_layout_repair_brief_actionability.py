from tools.quality_repair_checkers.layout_repair_brief_model import (
    build_layout_repair_brief,
    build_layout_repair_contract,
)


def test_label_shape_risk_is_not_sdk_actionable() -> None:
    brief = build_layout_repair_brief(
        {
            "status": "layout_failed",
            "pass": False,
            "blocking_layout_issue_count": 1,
            "top_blocking_issues": [
                {
                    "category": "label_shape_overlap_risk",
                    "ratio_of_smaller": 0.9,
                    "x_overlap": 0.0,
                    "y_overlap": 0.2,
                    "a": {
                        "path": "mobjects.line",
                        "class": "Line",
                        "kind": "shape",
                        "bbox": {"left": -3.0, "right": 3.0, "top": 0.1, "bottom": -0.1, "center_x": 0.0, "center_y": 0.0},
                    },
                    "b": {
                        "path": "mobjects.label",
                        "class": "MathTex",
                        "kind": "formula",
                        "text": "A_1",
                        "bbox": {"left": 2.8, "right": 3.1, "top": 0.2, "bottom": -0.1, "center_x": 2.95, "center_y": 0.05},
                    },
                }
            ],
        }
    )
    contract = build_layout_repair_contract(brief)

    assert brief["raw_blocking_count"] == 1
    assert brief["blocking_count"] == 0
    assert brief["sdk_actionable_blocking_count"] == 0
    assert brief["ignored_issue_count"] == 1
    assert brief["ignored_reason_counts"] == {"label_shape_overlap_risk": 1}
    assert brief["ignored_issues"][0]["reason"] == "label_shape_overlap_risk"
    assert brief["summary"]["primary_failure_type"] == "no_sdk_actionable_layout_issue"
    assert contract["active_cluster_policy"]["default"] == "no_sdk_actionable_repair"
    assert contract["clusters"] == []


def test_single_frame_bounds_overflow_is_not_sdk_actionable() -> None:
    brief = build_layout_repair_brief(
        {
            "status": "layout_failed",
            "pass": False,
            "blocking_layout_issue_count": 1,
            "top_blocking_issues": [
                {
                    "category": "frame_bounds_overflow",
                    "ratio_of_smaller": 1.0,
                    "a": {
                        "path": "mobjects.formula",
                        "class": "MathTex",
                        "kind": "formula",
                        "text": "y=3x-6",
                        "bbox": {"left": -30.0, "right": 30.0, "top": 2.0, "bottom": 1.5, "center_x": 0.0, "center_y": 1.75},
                    },
                }
            ],
        }
    )

    assert brief["raw_blocking_count"] == 1
    assert brief["sdk_actionable_blocking_count"] == 0
    assert brief["ignored_issues"][0]["reason"] == "frame_bounds_overflow_risk"


def test_text_formula_overlap_remains_sdk_actionable() -> None:
    brief = build_layout_repair_brief(
        {
            "status": "layout_failed",
            "pass": False,
            "blocking_layout_issue_count": 1,
            "top_blocking_issues": [
                {
                    "category": "text_formula_overlap",
                    "step": 12,
                    "ratio_of_smaller": 0.65,
                    "x_overlap": 1.1,
                    "y_overlap": 0.3,
                    "a": {
                        "path": "mobjects.text",
                        "class": "Text",
                        "kind": "text",
                        "text": "三角形面积：",
                        "bbox": {"left": 1.8, "right": 3.2, "top": 0.7, "bottom": 0.3, "center_x": 2.5, "center_y": 0.5},
                    },
                    "b": {
                        "path": "mobjects.formula",
                        "class": "MathTex",
                        "kind": "formula",
                        "text": "S=\\frac12 ab",
                        "bbox": {"left": 2.1, "right": 4.0, "top": 0.6, "bottom": 0.2, "center_x": 3.05, "center_y": 0.4},
                    },
                }
            ],
        }
    )
    contract = build_layout_repair_contract(brief)

    assert brief["raw_blocking_count"] == 1
    assert brief["sdk_actionable_blocking_count"] == 1
    assert brief["ignored_issue_count"] == 0
    assert brief["clusters"]
    assert contract["active_cluster_policy"]["default"] != "no_sdk_actionable_repair"
