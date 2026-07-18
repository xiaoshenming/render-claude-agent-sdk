import json

from tools.quality_repair_checkers.layout_repair_brief import (
    build_layout_repair_brief,
    build_layout_repair_contract,
)


def _obj(path, kind, text, x, y, cls="Text"):
    return {
        "path": path,
        "class": cls,
        "kind": kind,
        "text": text,
        "bbox": {
            "left": x - 0.2,
            "right": x + 0.2,
            "top": y + 0.1,
            "bottom": y - 0.1,
            "width": 0.4,
            "height": 0.2,
            "center_x": x,
            "center_y": y,
        },
    }


def _issue(a, b, *, step=1, category="text_formula_overlap", ratio=1.0):
    return {
        "category": category,
        "step": step,
        "event": "after_play",
        "ratio_of_smaller": ratio,
        "a": a,
        "b": b,
        "time_window": {"start": float(step), "end": float(step) + 0.5, "recommended_timestamp": float(step) + 0.25},
    }


def test_brief_detects_same_origin_text_stack_and_contract_keeps_evidence_separate():
    objects = [_obj(f"mobjects.{idx}", "text", name, 0.0, -0.58) for idx, name in enumerate(["小橘", "小白", "小花", "小黑", "狸狸"], 1)]
    issues = [_issue(a, b) for i, a in enumerate(objects) for b in objects[i + 1 :]]
    context = {
        "status": "layout_failed",
        "pass": False,
        "active_visible_objects": objects,
        "blocking_layout_issue_count": len(issues),
        "top_blocking_issues": issues,
    }

    brief = build_layout_repair_brief(context, case_id="names")
    contract = build_layout_repair_contract(brief)

    assert brief["clusters"][0]["failure_type"] == "same_origin_text_stack"
    assert brief["clusters"][0]["confidence"] >= 0.75
    assert brief["clusters"][0]["evidence"][0]["objects"][0]["text"] == "小橘"
    assert contract["active_cluster_policy"]["default"] == "repair_priority_1_only"
    assert "evidence" not in json.dumps(contract, ensure_ascii=False)
    assert "arrange" in " ".join(contract["clusters"][0]["preferred_patch"])


def test_brief_detects_step_panel_lifecycle_accumulation():
    issues = []
    for idx, step in enumerate([12, 18, 24, 30, 36, 42, 48, 54], 1):
        a = _obj(f"mobjects.{idx}", "text", f"推导步骤 {idx}", 2.6, 0.4 - idx * 0.03)
        b = _obj(f"mobjects.{idx + 20}", "formula", f"x_{idx}=y_{idx}", 2.7, 0.35 - idx * 0.03, cls="MathTex")
        issues.append(_issue(a, b, step=step, ratio=0.86))
    context = {
        "status": "layout_failed",
        "pass": False,
        "active_visible_objects": [item[key] for item in issues for key in ("a", "b")],
        "blocking_layout_issue_count": len(issues),
        "top_blocking_issues": issues,
    }

    brief = build_layout_repair_brief(context, case_id="panels")

    assert brief["clusters"][0]["failure_type"] == "step_panel_lifecycle_accumulation"
    assert brief["clusters"][0]["affected_region"] == "right_panel"
    assert brief["clusters"][0]["confidence"] >= 0.7
    assert "旧面板" in brief["clusters"][0]["root_cause"]


def test_brief_classifies_small_right_panel_text_formula_lifecycle_cluster():
    label = _obj("mobjects.geo_label", "text", "B", -4.8, -0.7)
    shape = _obj("mobjects.geo_line", "shape", "", -4.1, -0.2, cls="Line")
    stem = _obj("mobjects.problem_panel.stem", "text", "已知 AB=AC，求角 A", 2.4, 0.7)
    formula_1 = _obj("mobjects.step_panel.formula_1", "formula", r"\angle B=\angle C", 2.65, 0.66, cls="MathTex")
    formula_2 = _obj("mobjects.step_panel.formula_2", "formula", r"\angle A=40^\circ", 2.7, 0.5, cls="MathTex")
    context = {
        "status": "layout_failed",
        "pass": False,
        "active_visible_objects": [label, shape, stem, formula_1, formula_2],
        "blocking_layout_issue_count": 3,
        "top_blocking_issues": [
            _issue(shape, label, step=4, category="label_shape_overlap_risk", ratio=0.95),
            _issue(stem, formula_1, step=16, category="text_formula_overlap", ratio=0.88),
            _issue(stem, formula_2, step=24, category="text_formula_overlap", ratio=0.82),
        ],
    }

    brief = build_layout_repair_brief(context, case_id="right-panel-small")

    assert brief["clusters"][0]["failure_type"] == "label_shape_overlap"
    assert brief["clusters"][1]["failure_type"] == "step_panel_lifecycle_accumulation"
    assert brief["clusters"][1]["affected_region"] == "right_panel"
    assert "right_panel" in brief["clusters"][1]["root_cause"]
    assert "旧面板" in brief["clusters"][1]["root_cause"]


def test_contract_allows_same_round_repair_for_multiple_high_confidence_clusters():
    label = _obj("mobjects.geo_label", "text", "B", -4.8, -0.7)
    shape = _obj("mobjects.geo_line", "shape", "", -4.1, -0.2, cls="Line")
    stem = _obj("mobjects.problem_panel.stem", "text", "已知 AB=AC，求角 A", 2.4, 0.7)
    formula_1 = _obj("mobjects.step_panel.formula_1", "formula", r"\angle B=\angle C", 2.65, 0.66, cls="MathTex")
    formula_2 = _obj("mobjects.step_panel.formula_2", "formula", r"\angle A=40^\circ", 2.7, 0.5, cls="MathTex")
    context = {
        "status": "layout_failed",
        "pass": False,
        "active_visible_objects": [label, shape, stem, formula_1, formula_2],
        "blocking_layout_issue_count": 3,
        "top_blocking_issues": [
            _issue(shape, label, step=4, category="label_shape_overlap_risk", ratio=0.95),
            _issue(stem, formula_1, step=16, category="text_formula_overlap", ratio=0.88),
            _issue(stem, formula_2, step=24, category="text_formula_overlap", ratio=0.82),
        ],
    }

    brief = build_layout_repair_brief(context, case_id="right-panel-contract")
    contract = build_layout_repair_contract(brief)

    assert contract["active_cluster_policy"]["default"] == "repair_all_high_confidence_clusters"
    assert contract["clusters"][0]["repair_scope"] == "active_same_round"
    assert contract["clusters"][1]["cluster_id"] == "C02"
    assert contract["clusters"][1]["failure_type"] == "step_panel_lifecycle_accumulation"
    assert contract["clusters"][1]["repair_scope"] == "active_same_round"


def test_brief_detects_label_shape_overlap():
    label = _obj("mobjects.3", "text", "B", -4.8, -0.7)
    shape = _obj("mobjects.1.4", "shape", "", -4.1, -0.2, cls="Line")
    context = {
        "status": "layout_failed",
        "pass": False,
        "active_visible_objects": [label, shape],
        "blocking_layout_issue_count": 1,
        "top_blocking_issues": [
            _issue(shape, label, category="label_shape_overlap_risk", ratio=1.0),
        ],
    }

    brief = build_layout_repair_brief(context, case_id="label")
    contract = build_layout_repair_contract(brief)

    assert brief["clusters"][0]["failure_type"] == "label_shape_overlap"
    assert brief["clusters"][0]["affected_region"] == "left_panel"
    assert any("标签" in item for item in contract["clusters"][0]["must_fix"])


def test_brief_prioritizes_high_ratio_same_origin_over_low_ratio_container_noise():
    b = _obj("mobjects.2", "formula", "B. 2", -3.0, 2.9, cls="MathTex")
    c = _obj("mobjects.3", "formula", "C. \\sqrt{3}", -3.0, 2.9, cls="MathTex")
    d = _obj("mobjects.4", "formula", "D. \\sqrt{6}", -3.0, 2.9, cls="MathTex")
    rect = _obj("mobjects.9", "shape", "", -2.8, 2.9, cls="Rectangle")
    low_noise = [
        _issue(rect, _obj(f"mobjects.{idx}", "formula", f"noise {idx}", -2.8, 2.9, cls="MathTex"), category="label_shape_overlap_risk", ratio=0.1)
        for idx in range(10, 15)
    ]
    context = {
        "status": "layout_failed",
        "pass": False,
        "active_visible_objects": [b, c, d, rect],
        "blocking_layout_issue_count": 8,
        "top_blocking_issues": [
            _issue(b, c, ratio=0.95),
            _issue(b, d, ratio=0.95),
            _issue(c, d, ratio=0.95),
            *low_noise,
        ],
    }

    brief = build_layout_repair_brief(context, case_id="mixed")

    assert brief["clusters"][0]["failure_type"] == "same_origin_text_stack"
