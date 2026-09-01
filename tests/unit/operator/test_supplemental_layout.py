from manim_quality.operator.runtime_tools.supplemental_layout import (
    merge_supplemental_issues,
)


def test_restores_filtered_text_overlap_above_readability_threshold() -> None:
    raw = probe(overlap("预算有限时", "x=1", ratio=0.1032))

    merged = merge_supplemental_issues(raw, detector())

    assert len(merged["issues"]) == 1
    assert merged["issues"][0]["category"] == "text_formula_overlap"
    assert merged["raw"]["supplemental_issue_count"] == 1


def test_keeps_tiny_text_edge_touch_filtered() -> None:
    raw = probe(overlap("相邻", "x", ratio=0.05))

    assert merge_supplemental_issues(raw, detector())["issues"] == []


def test_restores_any_visible_text_frame_overflow() -> None:
    raw = {
        **probe(),
        "top_bounds_violations": [
            {
                "category": "frame_bounds_overflow",
                "step": 1,
                "event": "after_play",
                "overflow_x": 0.0075,
                "overflow_y": 0.0,
                "sides": ["left"],
                "object": object_("乙商品", "text", "Text", "mobjects.5.4"),
            }
        ],
    }

    merged = merge_supplemental_issues(raw, detector())

    assert merged["issues"][0]["category"] == "frame_bounds_overflow"


def test_restores_cross_owner_formula_near_axes() -> None:
    issue = near_collision(
        object_("Axes", "shape", "Axes", "mobjects.3.1.0"),
        object_("所以，原方程组的解为 x=5,y=2", "formula", "MathTex", "mobjects.22"),
    )

    merged = merge_supplemental_issues(probe(issue), detector())

    assert merged["issues"][0]["category"] == "label_shape_overlap_risk"


def test_ignores_short_axis_label_near_its_axis() -> None:
    issue = near_collision(
        object_("Axes", "shape", "Axes", "mobjects.3.1.0"),
        object_("x", "formula", "MathTex", "mobjects.3.2"),
    )

    assert merge_supplemental_issues(probe(issue), detector())["issues"] == []


def test_ignores_long_text_near_generic_rectangle_without_contact() -> None:
    issue = near_collision(
        object_("Rectangle", "shape", "Rectangle", "mobjects.1.0"),
        object_("目标：求收入关系式与最大收益", "formula", "Tex", "mobjects.5"),
    )

    assert merge_supplemental_issues(probe(issue), detector())["issues"] == []


def test_does_not_duplicate_vendor_issue() -> None:
    issue = overlap("预算有限时", "x=1", ratio=0.1032)
    existing = normalized(issue)

    merged = merge_supplemental_issues(probe(issue), detector(existing))

    assert len(merged["issues"]) == 1
    assert merged["raw"]["supplemental_issue_count"] == 0


def probe(*issues):
    return {
        "snapshot_count": 1,
        "top_overlaps": list(issues),
        "top_bounds_violations": [],
    }


def detector(*issues):
    return {
        "ok": True,
        "passed": not issues,
        "blocking_count": len(issues),
        "issues": list(issues),
        "raw": {"raw_issue_count": len(issues)},
    }


def overlap(a: str, b: str, *, ratio: float):
    return {
        "category": "text_formula_overlap",
        "step": 2,
        "event": "after_play",
        "ratio_of_smaller": ratio,
        "x_overlap": 0.2,
        "y_overlap": 0.1,
        "a": object_(a, "text", "Text", "mobjects.4.5"),
        "b": object_(b, "formula", "MathTex", "mobjects.30"),
    }


def near_collision(a: dict, b: dict):
    return {
        "category": "label_shape_overlap_risk",
        "step": 3,
        "event": "after_play",
        "ratio_of_smaller": 0.1001,
        "x_overlap": 1.0,
        "y_overlap": 0.0,
        "metadata": {"near_collision": True, "gap": 0.1},
        "a": a,
        "b": b,
    }


def object_(text: str, kind: str, class_: str, path: str):
    return {
        "class": class_,
        "kind": kind,
        "text": text,
        "path": path,
        "bbox": {
            "left": 0.0,
            "right": 1.0,
            "top": 1.0,
            "bottom": 0.0,
            "width": 1.0,
            "height": 1.0,
            "center_x": 0.5,
            "center_y": 0.5,
        },
    }


def normalized(issue: dict):
    return {
        **issue,
        "a": issue["a"]["path"],
        "b": issue["b"]["path"],
        "a_raw": issue["a"],
        "b_raw": issue["b"],
    }
