from manim_quality.operator.runtime_tools.candidate_recovery import (
    recover_candidates,
)
from manim_quality.operator.runtime_tools.combined_capture import (
    _Capture,
    _visible_paths,
)
from manim_quality.operator.runtime_tools.issues import compact_layout_report
from manim_quality.operator.runtime_tools.semantic_rows import overlaps


def test_semantic_rows_restore_hidden_result_overlap() -> None:
    rows = [
        {"path": "mobjects.27", "text": r"\sqrt{25} = 5", "role": "body",
         "bbox": box(-3.4521, -2.0998, -0.9469, -1.3406)},
        {"path": "mobjects.31", "text": r"\text{原式} = -1-\sqrt3",
         "role": "result", "bbox": box(-3.5088, -0.7695, -0.9316, -1.3254)},
    ]

    issue = overlaps(rows)[0]

    assert issue["ratio_of_smaller"] == 0.9614
    assert issue["a"]["text"] == r"\sqrt{25} = 5"
    assert issue["b"]["role"] == "result"


def test_mid_animation_sampling_is_bounded_to_half_seconds() -> None:
    capture = object.__new__(_Capture)
    capture.last_frame_sample = -1.0
    observed = []
    capture.snapshot = lambda scene, event, **kwargs: observed.append(
        (event, kwargs.get("persist")))
    scene = type("Scene", (), {"renderer": type("Renderer", (), {"time": 1.0})()})()

    capture.snapshot_frame(scene)
    scene.renderer.time = 1.2
    capture.snapshot_frame(scene)
    scene.renderer.time = 1.5
    capture.snapshot_frame(scene)

    assert observed == [("during_play", False), ("during_play", False)]


def test_mid_animation_visibility_excludes_transparent_old_text() -> None:
    class Mob:
        def __init__(self, opacity, children=()):
            self.opacity = opacity
            self.submobjects = list(children)

        def get_opacity(self):
            return self.opacity

    old = Mob(0)
    new = Mob(1)
    scene = type("Scene", (), {"mobjects": [old, new]})()

    assert _visible_paths(scene) == {"mobjects.1"}


def test_recovered_candidates_still_use_existing_compact_limit() -> None:
    candidates = [
        {"category": "semantic_row_bbox_overlap", "ratio_of_smaller": 0.9,
         "x_overlap": 1, "y_overlap": 1, "step": index,
         "a": {"path": f"a.{index}", "text": f"a{index}"},
         "b": {"path": f"b.{index}", "text": f"b{index}"}}
        for index in range(30)
    ]

    payload = recover_candidates(
        {"semantic_row_overlaps": candidates},
        {"issues": [], "raw": {}},
    )
    report = compact_layout_report(payload)

    assert payload["raw"]["recovered_issue_count"] == 30
    assert report["blocking_count"] == 30
    assert report["returned_issue_count"] == 20
    assert report["truncated"] is True
    assert "agent_bbox_candidates" not in report


def test_low_ratio_real_text_overlap_is_recovered() -> None:
    candidate = {
        "category": "text_formula_overlap",
        "ratio_of_smaller": 0.1032,
        "x_overlap": 1.14,
        "y_overlap": 0.04,
        "a": {"path": "mobjects.4", "kind": "formula", "text": "200/x"},
        "b": {"path": "mobjects.30", "kind": "text", "text": "预算有限"},
    }

    result = recover_candidates(
        {"top_overlaps": [candidate]}, {"issues": [], "raw": {}},
    )

    assert len(result["issues"]) == 1
    assert result["issues"][0]["recovered_from_raw_bbox"] is True


def test_tiny_text_overflow_is_recovered() -> None:
    candidate = {
        "category": "frame_bounds_overflow",
        "overflow_x": 0.0075,
        "object": {"path": "mobjects.5", "kind": "text", "text": "乙商品"},
    }

    result = recover_candidates(
        {"top_bounds_violations": [candidate]}, {"issues": [], "raw": {}},
    )

    assert len(result["issues"]) == 1


def test_line_crossing_its_coordinate_label_is_not_recovered() -> None:
    candidate = {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1,
        "x_overlap": 1,
        "y_overlap": 0.2,
        "a": {"path": "mobjects.6", "kind": "shape", "class": "Line"},
        "b": {"path": "mobjects.19", "kind": "formula", "text": "A(40,2000)"},
    }

    result = recover_candidates(
        {"top_overlaps": [candidate]}, {"issues": [], "raw": {}},
    )

    assert result["issues"] == []


def test_actual_rectangle_label_contact_reaches_stroke_policy() -> None:
    candidate = {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1,
        "x_overlap": 0.3,
        "y_overlap": 0.2,
        "a": {"path": "mobjects.4", "kind": "shape", "class": "Rectangle"},
        "b": {"path": "mobjects.5", "kind": "formula", "text": "2.5"},
    }

    result = recover_candidates(
        {"top_overlaps": [candidate]}, {"issues": [], "raw": {}},
    )

    assert len(result["issues"]) == 1


def box(left, right, top, bottom):
    return {
        "left": left, "right": right, "top": top, "bottom": bottom,
        "width": right-left, "height": top-bottom,
    }
