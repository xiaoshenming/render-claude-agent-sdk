from manim_quality.operator.runtime_tools.candidate_facts import candidate_facts
from manim_quality.operator.runtime_tools.issues import compact_layout_report


def overlap(path, timestamp=1, ratio=0.01):
    return {"category": "text_formula_overlap", "ratio_of_smaller": ratio,
            "a": {"path": path, "kind": "text", "text": "same label"},
            "b": {"path": "scene.other", "kind": "formula", "text": "x=2"},
            "time_window": {"start": timestamp, "end": timestamp,
                            "recommended_timestamp": timestamp}}


def test_filtered_candidates_survive_and_same_text_is_not_object_identity():
    probe = {"top_overlaps": [overlap("first"), overlap("second"),
                              overlap("first", timestamp=4, ratio=0.8)]}
    report = candidate_facts(probe, {"issues": [], "passed": True})
    compact = compact_layout_report(report)
    assert compact["candidate_count"] == 2
    assert compact["probe_summary"]["raw_issue_count"] == 3
    assert compact["issues"][0]["phase"]["time_window"]["end"] == 4
    assert compact["issues"][0]["severity"] == "candidate"
    assert compact["blocking_count"] == 0
    assert compact["evidence_only"] is True


def test_compact_output_bounded_and_complete_candidates_retained():
    import json
    rows = [overlap(str(i)) for i in range(100)]
    for row in rows:
        row["a"]["text"] = "long equation " * 1000
    report = candidate_facts({"top_overlaps": rows}, {"issues": []})
    compact = compact_layout_report(report)
    assert len(report["issues"]) == 100
    assert compact["truncated"] is True
    assert compact["returned_issue_count"] <= 20
    assert len(json.dumps(compact, ensure_ascii=False)) <= 24_000
    assert compact["issues"][0]["objects"][0]["text_truncated"] is True


def test_display_bounds_include_vertices_after_the_old_160_point_limit():
    from types import SimpleNamespace
    from manim_quality.operator.runtime_tools.display_bounds import install_complete_bounds
    delegate = SimpleNamespace(
        _display_bbox_of=lambda *a, **kw: {"right": 1},
        _display_points2=lambda scene, mob, values, max_points: values[:max_points],
        _bbox_from_points2=lambda points: {"right": max(p[0] for p in points)},
    )
    install_complete_bounds(delegate)
    mob = SimpleNamespace(get_all_points=lambda: [[1, 0, 0]] * 160 + [[9, 0, 0]])
    assert delegate._display_bbox_of(None, mob, {})["right"] == 9
