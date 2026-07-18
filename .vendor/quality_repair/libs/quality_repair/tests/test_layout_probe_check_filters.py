from tools.quality_repair_checkers.layout_probe_check import _is_repair_blocking_issue


def test_layout_probe_filter_ignores_thin_formula_rectangle_overlap() -> None:
    issue = {
        "category": "label_shape_overlap_risk",
        "a": {
            "class": "MathTex",
            "kind": "formula",
            "text": "a = \\frac{2}{\\sqrt{5}-\\sqrt{3}}",
            "path": "mobjects.2",
            "bbox": {"width": 1.8, "height": 0.7},
        },
        "b": {
            "class": "Rectangle",
            "kind": "shape",
            "path": "mobjects.8.0.9",
            "bbox": {"width": 0.1531, "height": 0.0123},
        },
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_ignores_formula_parent_child_overlap() -> None:
    issue = {
        "category": "text_formula_overlap",
        "a": {"class": "MathTex", "kind": "formula", "path": "mobjects.8"},
        "b": {"class": "SingleStringMathTex", "kind": "formula", "path": "mobjects.8.0"},
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_ignores_low_ratio_adjacent_formula_touch() -> None:
    issue = {
        "category": "text_formula_overlap",
        "ratio_of_smaller": 0.13,
        "a": {"class": "MathTex", "kind": "formula", "text": "= \\frac{2}{2}", "path": "mobjects.1"},
        "b": {"class": "MathTex", "kind": "formula", "text": "= \\frac{2(\\sqrt{5})}{2}", "path": "mobjects.2"},
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_keeps_large_formula_overlap() -> None:
    issue = {
        "category": "text_formula_overlap",
        "ratio_of_smaller": 0.42,
        "a": {"class": "MathTex", "kind": "formula", "text": "= \\frac{2}{2}", "path": "mobjects.1"},
        "b": {"class": "MathTex", "kind": "formula", "text": "= \\frac{2(\\sqrt{5})}{2}", "path": "mobjects.2"},
    }

    assert _is_repair_blocking_issue(issue) is True


def test_layout_probe_filter_ignores_low_ratio_text_formula_edge_touch() -> None:
    issue = {
        "category": "text_formula_overlap",
        "ratio_of_smaller": 0.0669,
        "a": {"class": "MathTex", "kind": "formula", "text": "\\text{非负性}"},
        "b": {"class": "MathTex", "kind": "formula", "text": "\\text{不符合}"},
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_ignores_coordinate_label_over_transparent_region() -> None:
    issue = {
        "category": "label_shape_overlap_risk",
        "a": {
            "class": "Text",
            "kind": "text",
            "text": "D(0,1)",
            "bbox": {"width": 0.86, "height": 0.29},
        },
        "b": {
            "class": "Polygon",
            "kind": "shape",
            "bbox": {"width": 3.13, "height": 1.09},
        },
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_ignores_coordinate_label_axis_touch() -> None:
    issue = {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 0.1531,
        "a": {
            "class": "Arrow",
            "kind": "shape",
            "bbox": {"width": 0.1756, "height": 4.39},
        },
        "b": {
            "class": "Text",
            "kind": "text",
            "text": "B(2,0)",
            "bbox": {"width": 0.8672, "height": 0.293},
        },
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_ignores_bbox_only_diagonal_line_label_overlap() -> None:
    issue = {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1.0,
        "a": {
            "class": "Text",
            "kind": "text",
            "text": "D(0,1)",
            "bbox": {"width": 0.8664, "height": 0.293},
        },
        "b": {
            "class": "Line",
            "kind": "shape",
            "bbox": {"width": 3.654, "height": 3.8412},
        },
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_keeps_thin_axis_label_overlap() -> None:
    issue = {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1.0,
        "a": {
            "class": "Text",
            "kind": "text",
            "text": "D(0,1)",
            "bbox": {"width": 0.8664, "height": 0.293},
        },
        "b": {
            "class": "Arrow",
            "kind": "shape",
            "bbox": {"width": 0.1756, "height": 4.39},
        },
    }

    assert _is_repair_blocking_issue(issue) is True


def test_layout_probe_filter_ignores_highlight_rectangle_as_container_overflow() -> None:
    issue = {
        "category": "text_container_overflow",
        "ratio_of_smaller": 0.747,
        "a": {
            "class": "MathTex",
            "kind": "formula",
            "text": "= |a-4| + |11-a|",
            "bbox": {"width": 2.4, "height": 0.38},
        },
        "b": {
            "class": "SurroundingRectangle",
            "kind": "shape",
            "bbox": {"width": 0.7, "height": 0.45},
        },
    }

    assert _is_repair_blocking_issue(issue) is False


def test_layout_probe_filter_ignores_formula_cancellation_line() -> None:
    issue = {
        "category": "label_shape_overlap_risk",
        "ratio_of_smaller": 1.0,
        "a": {
            "class": "Text",
            "kind": "text",
            "text": "= \\frac{6(3\\sqrt{2}+2\\sqrt{3})}{6}",
            "bbox": {"width": 3.8, "height": 0.7},
        },
        "b": {
            "class": "Line",
            "kind": "shape",
            "bbox": {"width": 0.8, "height": 0.2},
        },
    }

    assert _is_repair_blocking_issue(issue) is False
