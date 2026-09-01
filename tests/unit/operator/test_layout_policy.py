"""Versioned layout policy: downgrade only provably stroke-free contained labels."""

import json
from pathlib import Path

from manim_quality.operator.runtime_tools.issues import compact_layout_report
from manim_quality.operator.runtime_tools.layout_policy import (
    LAYOUT_POLICY_VERSION,
    evaluate_downgrade,
    load_geometry_sidecar,
)


def _issue(
    *,
    step: int = 11,
    shape_class: str = "Polygon",
    shape_bbox: dict[str, float],
    text_bbox: dict[str, float],
    shape_path: str = "mobjects.2",
) -> dict[str, object]:
    return {
        "scene": "Solution",
        "step": step,
        "event": "after_play",
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1.0,
        "a_raw": {
            "class": shape_class,
            "kind": "shape",
            "text": "",
            "path": shape_path,
            "bbox": shape_bbox,
        },
        "b_raw": {
            "class": "MathTex",
            "kind": "formula",
            "text": "40^\\circ",
            "path": "mobjects.12",
            "bbox": text_bbox,
        },
    }


def _sidecar(step: int, path: str, geometry: dict[str, object]) -> dict[str, object]:
    return {
        "version": 1,
        "captures": [
            {"step": step, "shapes": [{"path": path, "class": "Polygon", "geometry": geometry}]}
        ],
    }


# Real batch MQ-timeout5-v3-183954 sample 035, revision R3, step 11.
# Display-space bboxes are verbatim from bbox_probe.json / layout_detector.json.
# The triangle's display vertices are reconstructed from the candidate source
# (B/C on the bottom edge, apex above) and reproduce the probed Polygon bbox
# and the probed height-line bbox corners to 1e-4.
REAL_035_SHAPE_BBOX = {
    "left": -4.8489, "right": -1.8489, "top": 1.0463, "bottom": -2.1705,
}
REAL_035_TEXT_BBOX = {
    "left": -4.8084, "right": -4.2955, "top": -1.7267, "bottom": -2.0203,
}
REAL_035_VERTICES = [
    [-3.3489, 1.0463],
    [-4.8489, -2.1705],
    [-1.8489, -2.1705],
]


def test_real_035_contained_label_is_not_downgraded_because_edge_crosses_bbox() -> None:
    """Honest regression on the real 035 geometry.

    The 40-degree label bbox is fully inside the Polygon bbox, but the edge
    from the apex to the bottom-left vertex enters the label bbox through its
    bottom edge at x=-4.7789 and exits through its top edge at x=-4.6421.
    The policy therefore must keep the issue blocking (a spot check of only
    the bottom edge and of the slanted edge at the label's center x misses
    this crossing).
    """
    issue = _issue(shape_bbox=REAL_035_SHAPE_BBOX, text_bbox=REAL_035_TEXT_BBOX)
    sidecar = _sidecar(
        11,
        "mobjects.2",
        {"type": "polygon", "filled": False, "points": REAL_035_VERTICES},
    )

    assert evaluate_downgrade(issue, sidecar) is None


# Real batch sample 042, revision R3, step 1: the "B" vertex label genuinely
# grazes the outgoing Line near the vertex. Its bbox is not contained in the
# Line bbox, so containment alone must already refuse the downgrade.
def test_real_042_vertex_label_touching_line_is_not_downgraded() -> None:
    issue = _issue(
        step=1,
        shape_class="Line",
        shape_path="mobjects.2.3",
        shape_bbox={
            "left": -4.9993, "right": -3.0773, "top": 0.2263, "bottom": -1.12,
        },
        text_bbox={
            "left": -4.8455, "right": -4.4852, "top": -0.9477, "bottom": -1.2923,
        },
    )
    sidecar = _sidecar(
        1,
        "mobjects.2.3",
        {"type": "line", "points": [[-4.9993, -1.12], [-3.0773, 0.2263]]},
    )

    assert evaluate_downgrade(issue, sidecar) is None


_BIG_TRIANGLE = {
    "shape_bbox": {"left": -4.0, "right": 4.0, "top": 3.0, "bottom": -3.0},
    "text_bbox": {"left": -0.25, "right": 0.25, "top": -0.85, "bottom": -1.15},
}
_BIG_TRIANGLE_VERTICES = [[0.0, 3.0], [-4.0, -3.0], [4.0, -3.0]]


def test_contained_label_clear_of_every_edge_is_downgraded_with_versioned_reason() -> None:
    issue = _issue(**_BIG_TRIANGLE)
    sidecar = _sidecar(
        11,
        "mobjects.2",
        {"type": "polygon", "filled": True, "points": _BIG_TRIANGLE_VERTICES},
    )

    policy = evaluate_downgrade(issue, sidecar)

    assert policy is not None
    assert policy["id"] == "contained_label_no_stroke_contact"
    assert policy["version"] == LAYOUT_POLICY_VERSION
    assert policy["margin"] > 0


def test_label_bbox_crossing_an_edge_is_never_downgraded() -> None:
    issue = _issue(
        shape_bbox=_BIG_TRIANGLE["shape_bbox"],
        # Straddles the bottom edge y=-3 while staying inside the shape bbox.
        text_bbox={"left": -0.25, "right": 0.25, "top": -2.9, "bottom": -3.0},
    )
    sidecar = _sidecar(
        11,
        "mobjects.2",
        {"type": "polygon", "filled": True, "points": _BIG_TRIANGLE_VERTICES},
    )

    assert evaluate_downgrade(issue, sidecar) is None


def test_label_inside_safety_margin_of_an_edge_is_never_downgraded() -> None:
    issue = _issue(
        shape_bbox=_BIG_TRIANGLE["shape_bbox"],
        # 0.02 above the bottom edge: closer than the 0.03 safety margin.
        text_bbox={"left": -0.25, "right": 0.25, "top": -2.68, "bottom": -2.98},
    )
    sidecar = _sidecar(
        11,
        "mobjects.2",
        {"type": "polygon", "filled": True, "points": _BIG_TRIANGLE_VERTICES},
    )

    assert evaluate_downgrade(issue, sidecar) is None


def test_narrow_centered_label_near_edge_is_not_downgraded() -> None:
    issue = _issue(
        shape_class="Rectangle",
        shape_path="mobjects.4.3",
        shape_bbox={"left": -0.21, "right": 0.21, "top": 0.58, "bottom": -0.58},
        text_bbox={"left": -0.19, "right": 0.19, "top": 0.12, "bottom": -0.12},
    )
    sidecar = _sidecar(
        11,
        "mobjects.4.3",
        {"type": "polygon", "points": [
            [-0.21, -0.58], [0.21, -0.58], [0.21, 0.58], [-0.21, 0.58],
        ]},
    )

    assert evaluate_downgrade(issue, sidecar) is None


def test_missing_vertex_data_fails_closed() -> None:
    issue = _issue(**_BIG_TRIANGLE)

    assert evaluate_downgrade(issue, None) is None
    assert evaluate_downgrade(issue, {"version": 1, "captures": []}) is None
    assert (
        evaluate_downgrade(issue, _sidecar(11, "mobjects.2", {"type": "polygon"}))
        is None
    )
    assert (
        evaluate_downgrade(
            issue,
            _sidecar(11, "mobjects.2", {"type": "polygon", "points": [[0.0, 3.0]]}),
        )
        is None
    )


def test_step_mismatch_fails_closed() -> None:
    issue = _issue(**_BIG_TRIANGLE)
    sidecar = _sidecar(
        12,
        "mobjects.2",
        {"type": "polygon", "filled": True, "points": _BIG_TRIANGLE_VERTICES},
    )

    assert evaluate_downgrade(issue, sidecar) is None


def test_shape_shape_and_text_text_pairs_are_out_of_policy_scope() -> None:
    issue = _issue(**_BIG_TRIANGLE)
    issue["b_raw"] = dict(issue["b_raw"], kind="shape")
    sidecar = _sidecar(
        11,
        "mobjects.2",
        {"type": "polygon", "filled": True, "points": _BIG_TRIANGLE_VERTICES},
    )

    assert evaluate_downgrade(issue, sidecar) is None


def test_compact_report_excludes_downgraded_issue_from_blocking_count() -> None:
    blocking = _issue(shape_bbox=REAL_035_SHAPE_BBOX, text_bbox=REAL_035_TEXT_BBOX)
    downgraded = _issue(**_BIG_TRIANGLE, shape_path="mobjects.7")
    sidecar = _sidecar(
        11,
        "mobjects.7",
        {"type": "polygon", "filled": True, "points": _BIG_TRIANGLE_VERTICES},
    )

    report = compact_layout_report(
        {"issues": [blocking, downgraded]},
        geometry_sidecar=sidecar,
    )

    assert report["blocking_count"] == 1
    assert report["downgraded_count"] == 1
    assert report["layout_policy_version"] == LAYOUT_POLICY_VERSION
    assert len(report["issues"]) == 2
    severities = [item["severity"] for item in report["issues"]]
    assert severities == ["blocking", "warning"]
    warning = report["issues"][1]
    assert warning["policy"]["id"] == "contained_label_no_stroke_contact"
    assert warning["category"] == "label_shape_overlap_risk"
    assert "policy" not in report["issues"][0]


def test_compact_report_without_sidecar_keeps_every_issue_blocking() -> None:
    report = compact_layout_report({"issues": [_issue(**_BIG_TRIANGLE)]})

    assert report["blocking_count"] == 1
    assert report["downgraded_count"] == 0


def test_load_geometry_sidecar_rejects_missing_or_malformed_files(tmp_path: Path) -> None:
    assert load_geometry_sidecar(tmp_path / "absent.json") is None
    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    assert load_geometry_sidecar(broken) is None
    listy = tmp_path / "list.json"
    listy.write_text("[1, 2]", encoding="utf-8")
    assert load_geometry_sidecar(listy) is None
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"version": 1, "captures": []}), encoding="utf-8")
    assert load_geometry_sidecar(good) == {"version": 1, "captures": []}
