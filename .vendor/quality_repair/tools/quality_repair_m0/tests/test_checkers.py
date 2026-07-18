import json
import subprocess
import sys
from pathlib import Path

from tools.quality_repair_checkers.layout_probe_check import payload_from_probe


LOGIC_CHECK = Path(__file__).resolve().parents[2] / "quality_repair_checkers" / "logic_contract_check.py"


def test_logic_contract_check_detects_and_passes_equal_length(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    facts = workdir / "facts"
    facts.mkdir(parents=True)
    (facts / "logic_contract.json").write_text(
        json.dumps(
            {
                "scene_name": "Scene_01",
                "contracts": [
                    {"kind": "equal_length", "segment_a": ["p1", "p2"], "segment_b": ["p3", "p4"], "move_point": "p4"}
                ],
                "before_validation": {
                    "issues": [
                        {
                            "target": "p4",
                            "evidence": {
                                "expected_coords": [4.0, -2.3, 0.0],
                                "actual_coords": [4.0, -1.8, 0.0],
                                "reference_length": 2.5,
                            },
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    code = workdir / "candidate.py"
    code.write_text(
        "import numpy as np\n"
        "class Scene_01:\n"
        "    def construct(self):\n"
        "        p1 = np.array([-4, -2.3, 0])\n"
        "        p2 = np.array([-1.5, -2.8, 0])\n"
        "        p3 = np.array([1.5, -2.8, 0])\n"
        "        p4 = np.array([4, -1.8, 0])\n",
        encoding="utf-8",
    )

    failed = _run_logic_check(code, workdir)
    assert failed["passed"] is False
    assert failed["blocking_count"] == 1
    assert failed["issues"][0]["kind"] == "point_coordinate_wrong"

    code.write_text(code.read_text(encoding="utf-8").replace("[4, -1.8, 0]", "[4.0, -2.3, 0.0]"), encoding="utf-8")
    passed = _run_logic_check(code, workdir)
    assert passed["passed"] is True
    assert passed["blocking_count"] == 0


def test_logic_contract_check_extracts_make_point_by_coord(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    facts = workdir / "facts"
    facts.mkdir(parents=True)
    (facts / "logic_contract.json").write_text(
        json.dumps(
            {
                "scene_name": "Solution",
                "contracts": [
                    {"kind": "point_coordinate", "target": "dot_P4", "expected_coords": [0, 6, 0]}
                ],
            }
        ),
        encoding="utf-8",
    )
    code = workdir / "candidate.py"
    code.write_text(
        "class Solution:\n"
        "    def construct(self):\n"
        "        dot_P4 = self.make_point_by_coord(0, 5)\n",
        encoding="utf-8",
    )

    failed = _run_logic_check(code, workdir)
    assert failed["passed"] is False
    assert failed["issues"][0]["kind"] == "point_coordinate_wrong"
    assert failed["issues"][0]["actual_coords"] == [0.0, 5.0, 0.0]

    code.write_text(code.read_text(encoding="utf-8").replace("(0, 5)", "(0, 6)"), encoding="utf-8")
    passed = _run_logic_check(code, workdir)
    assert passed["passed"] is True


def test_logic_contract_check_extracts_fractional_make_point_by_coord(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    facts = workdir / "facts"
    facts.mkdir(parents=True)
    (facts / "logic_contract.json").write_text(
        json.dumps(
            {
                "scene_name": "Solution",
                "contracts": [
                    {"kind": "point_coordinate", "target": "dot_P2", "expected_coords": [0, 10 / 3, 0]}
                ],
            }
        ),
        encoding="utf-8",
    )
    code = workdir / "candidate.py"
    code.write_text(
        "class Solution:\n"
        "    def construct(self):\n"
        "        dot_P2 = self.make_point_by_coord(0, 10/3)\n",
        encoding="utf-8",
    )

    passed = _run_logic_check(code, workdir)
    assert passed["passed"] is True


def test_logic_contract_check_source_contains_and_forbids_text(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    facts = workdir / "facts"
    facts.mkdir(parents=True)
    (facts / "logic_contract.json").write_text(
        json.dumps(
            {
                "scene_name": "Solution",
                "contracts": [
                    {"kind": "source_contains", "text": "6\\sqrt{3}"},
                    {"kind": "source_not_contains", "text": "最小值为2"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    code = workdir / "candidate.py"
    code.write_text(
        "class Solution:\n"
        "    def construct(self):\n"
        "        answer = '∴BM+MN的最小值为2'\n",
        encoding="utf-8",
    )

    failed = _run_logic_check(code, workdir)
    assert failed["passed"] is False
    assert {issue["kind"] for issue in failed["issues"]} == {"source_missing_text", "source_forbidden_text_present"}

    code.write_text(
        "class Solution:\n"
        "    def construct(self):\n"
        "        answer = '∴BM+MN的最小值为6\\\\sqrt{3}'\n",
        encoding="utf-8",
    )
    passed = _run_logic_check(code, workdir)
    assert passed["passed"] is True


def test_layout_probe_payload_maps_overlaps_to_blocking_count() -> None:
    payload = payload_from_probe(
        {
            "ok": True,
            "scene_name": "Demo",
            "top_overlaps": [{"kind": "overlap", "a": "A", "b": "B"}],
            "top_bounds_violations": [{"kind": "bounds", "object": "C"}],
            "snapshot_count": 3,
        }
    )

    assert payload["ok"] is True
    assert payload["passed"] is False
    assert payload["blocking_count"] == 2
    assert payload["raw"]["scene_name"] == "Demo"


def test_layout_probe_payload_normalizes_object_dicts_to_paths() -> None:
    payload = payload_from_probe(
        {
            "ok": True,
            "top_overlaps": [
                {
                    "kind": "overlap",
                    "a": {"path": "mobjects.14", "class": "MathTex"},
                    "b": {"path": "mobjects.24", "class": "Polygon"},
                }
            ],
            "top_bounds_violations": [],
        }
    )

    issue = payload["issues"][0]
    assert issue["a"] == "mobjects.14"
    assert issue["b"] == "mobjects.24"
    assert issue["a_raw"]["class"] == "MathTex"
    assert issue["b_raw"]["class"] == "Polygon"


def test_layout_probe_payload_ignores_non_blocking_radical_bar_gap() -> None:
    payload = payload_from_probe(
        {
            "ok": True,
            "top_overlaps": [
                {
                    "category": "label_shape_overlap_risk",
                    "metadata": {"near_collision": True, "gap": 0.25},
                    "x_overlap": 0.2,
                    "y_overlap": 0.0,
                    "a": {"path": "mobjects.1", "class": "Text", "kind": "text", "text": "选项 C"},
                    "b": {
                        "path": "mobjects.2.0.1",
                        "class": "Rectangle",
                        "kind": "shape",
                        "bbox": {"width": 0.2, "height": 0.008},
                    },
                },
                {
                    "category": "label_shape_overlap_risk",
                    "ratio_of_smaller": 1.0,
                    "x_overlap": 0.3,
                    "y_overlap": 0.2,
                    "a": {"path": "mobjects.3", "class": "Line", "kind": "shape"},
                    "b": {"path": "mobjects.4", "class": "Text", "kind": "text", "text": "A"},
                },
            ],
            "top_bounds_violations": [],
        }
    )

    assert payload["blocking_count"] == 1
    assert payload["raw"]["ignored_issue_count"] == 1
    assert payload["issues"][0]["a"] == "mobjects.3"


def test_layout_probe_payload_ignores_low_priority_near_collision() -> None:
    payload = payload_from_probe(
        {
            "ok": True,
            "top_overlaps": [
                {
                    "category": "label_shape_overlap_risk",
                    "ratio_of_smaller": 0.1001,
                    "metadata": {"near_collision": True, "gap": 0.08},
                    "x_overlap": 0.0,
                    "y_overlap": 0.29,
                    "a": {"path": "mobjects.3", "class": "Line", "kind": "shape"},
                    "b": {"path": "mobjects.4", "class": "Text", "kind": "text", "text": "B(3,0)"},
                },
                {
                    "category": "label_shape_overlap_risk",
                    "ratio_of_smaller": 0.6,
                    "x_overlap": 0.4,
                    "y_overlap": 0.2,
                    "a": {"path": "mobjects.5", "class": "Line", "kind": "shape"},
                    "b": {"path": "mobjects.6", "class": "Text", "kind": "text", "text": "C"},
                },
            ],
            "top_bounds_violations": [],
        }
    )

    assert payload["blocking_count"] == 1
    assert payload["raw"]["ignored_issue_count"] == 1
    assert payload["issues"][0]["a"] == "mobjects.5"


def test_layout_probe_payload_ignores_origin_label_on_axis() -> None:
    payload = payload_from_probe(
        {
            "ok": True,
            "top_overlaps": [
                {
                    "category": "label_shape_overlap_risk",
                    "ratio_of_smaller": 1.0,
                    "x_overlap": 0.14,
                    "y_overlap": 0.20,
                    "a": {"path": "mobjects.2.0", "class": "Arrow", "kind": "shape", "bbox": {"width": 5.2, "height": 0.2}},
                    "b": {"path": "mobjects.10", "class": "Text", "kind": "text", "text": "O", "bbox": {"width": 0.15, "height": 0.2}},
                }
            ],
            "top_bounds_violations": [],
        }
    )

    assert payload["passed"] is True
    assert payload["blocking_count"] == 0
    assert payload["raw"]["ignored_issue_count"] == 1


def test_layout_probe_payload_ignores_short_label_over_area_polygon() -> None:
    payload = payload_from_probe(
        {
            "ok": True,
            "top_overlaps": [
                {
                    "category": "label_shape_overlap_risk",
                    "ratio_of_smaller": 1.0,
                    "x_overlap": 0.15,
                    "y_overlap": 0.19,
                    "a": {"path": "mobjects.4", "class": "Text", "kind": "text", "text": "M", "bbox": {"width": 0.15, "height": 0.2}},
                    "b": {"path": "mobjects.20", "class": "Polygon", "kind": "shape", "bbox": {"width": 1.7, "height": 2.2}},
                }
            ],
            "top_bounds_violations": [],
        }
    )

    assert payload["passed"] is True
    assert payload["blocking_count"] == 0
    assert payload["raw"]["ignored_issue_count"] == 1


def test_layout_probe_payload_normalizes_bounds_object_as_issue_target() -> None:
    payload = payload_from_probe(
        {
            "ok": True,
            "top_overlaps": [],
            "top_bounds_violations": [
                {
                    "category": "frame_bounds_overflow",
                    "overflow_y": 0.25,
                    "object": {
                        "path": "mobjects.11",
                        "class": "MathTex",
                        "kind": "formula",
                        "bbox": {"bottom": -4.29, "top": -3.92, "left": -6, "right": -4},
                    },
                }
            ],
        }
    )

    assert payload["blocking_count"] == 1
    assert payload["issues"][0]["a"] == "mobjects.11"
    assert payload["issues"][0]["object"] == "mobjects.11"


def _run_logic_check(code: Path, workdir: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(LOGIC_CHECK), "--code", str(code), "--workdir", str(workdir)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)
