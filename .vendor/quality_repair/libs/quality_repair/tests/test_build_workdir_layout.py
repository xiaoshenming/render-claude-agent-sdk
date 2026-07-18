import json
from pathlib import Path

from libs.quality_repair import RepairBundle
from libs.quality_repair.contract import build_workdir
from libs.quality_repair.schemas import read_json


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_build_workdir_full_layout_bundle(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("from manim import *\n\nclass Scene_01(Scene):\n    def construct(self):\n        self.wait()\n", encoding="utf-8")
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "frame": {"x_min": -6.5, "x_max": 6.5, "y_min": -3.5, "y_max": 3.5},
            "objects": [{"id": "text1"}, {"id": "text2"}, {"name": "shape1"}],
            "collisions": [{"kind": "overlap", "a": "text1", "b": "text2"}],
        },
    )
    frame_png = tmp_path / "frame_01.png"
    frame_png.write_bytes(b"fake-png-bytes")

    dest = tmp_path / "workdir"
    result = build_workdir(RepairBundle(job_id="job-1", code_path=code, layout_context=layout_context, frames=[frame_png]), dest)

    assert result == dest
    assert (dest / "candidate.py").read_text(encoding="utf-8") == code.read_text(encoding="utf-8")
    assert (dest / "core_candidate.py").read_text(encoding="utf-8").startswith("class Scene_01(Scene):")
    assert (dest / "candidate_prelude.txt").read_text(encoding="utf-8") == "from manim import *\n\n"
    assert read_json(dest / "candidate_core_map.json")["enabled"] is True
    root_context = read_json(dest / "layout_context.json")
    assert root_context["blocking_layout_issue_count"] == 1
    assert root_context["top_blocking_issues"] == [{"kind": "overlap", "a": "text1", "b": "text2"}]
    brief = read_json(dest / "layout_repair_brief.json")
    contract = read_json(dest / "layout_repair_contract.json")
    digest = read_json(dest / "layout_issue_digest.json")
    assert brief["schema_version"] == "quality_repair.layout_repair_brief.v1"
    assert brief["blocking_count"] == 1
    assert contract["schema_version"] == "quality_repair.layout_repair_contract.v1"
    assert "layout_repair_brief.json" in contract["default_read_order"]
    assert digest["schema_version"] == "quality_repair.layout_issue_digest.issue_only.v1"
    assert digest["blocking_layout_issue_count"] == 1
    assert digest["issue_count"] == 1
    assert digest["issues"][0]["issue_id"] == "I001"
    assert digest["issues"][0]["kind"] == "overlap"
    assert "risk_hints" not in digest
    assert "issue_groups" not in digest
    assert "object_index" not in digest
    assert not (dest / "agent_safety_contract.json").exists()
    assert read_json(dest / "facts" / "layout_context.full.json")["collisions"][0]["a"] == "text1"
    assert not (dest / "TICKET.md").exists()
    assert "max_edit_calls" not in read_json(dest / "facts" / "protected.json")
    assert not (dest / "frames").exists()
    assert not (dest / "build_warnings.json").exists()


def test_build_workdir_digest_failure_keeps_legacy_brief_contract(tmp_path: Path, monkeypatch) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("class Scene_01:\n    pass\n", encoding="utf-8")
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "objects": [{"id": "text1"}, {"id": "text2"}],
            "collisions": [{"kind": "overlap", "a": "text1", "b": "text2"}],
        },
    )

    def boom(*args, **kwargs):
        raise RuntimeError("digest failed")

    monkeypatch.setattr("tools.quality_repair_checkers.layout_repair_brief.build_layout_issue_digest", boom)
    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="digest-fails", code_path=code, layout_context=layout_context), dest)

    assert read_json(dest / "layout_repair_brief.json")["schema_version"] == "quality_repair.layout_repair_brief.v1"
    assert read_json(dest / "layout_repair_contract.json")["schema_version"] == "quality_repair.layout_repair_contract.v1"
    assert not (dest / "layout_issue_digest.json").exists()
    assert "layout_issue_digest_generation_failed:digest failed" in read_json(dest / "build_warnings.json")["warnings"]


def test_build_workdir_missing_layout_context_uses_defaults(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("print('ok')\n", encoding="utf-8")

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="job-2", code_path=code), dest)

    assert (dest / "candidate.py").exists()
    assert not (dest / "layout_context.json").exists()
    assert not (dest / "facts").exists()
    assert "layout_context_not_provided" in read_json(dest / "build_warnings.json")["warnings"]


def test_build_workdir_normalizes_audit_layout_context(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("print('layout')\n", encoding="utf-8")
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "active_visible_objects": [
                {"path": "mobjects.11", "class": "Line"},
                {"path": "mobjects.13", "class": "Text", "text": "零"},
            ],
            "blocking_layout_issue_count": 1,
            "top_blocking_issues": [
                {
                    "category": "label_shape_overlap_risk",
                    "a": {"path": "mobjects.11", "class": "Line"},
                    "b": {"path": "mobjects.13", "class": "Text", "text": "零"},
                }
            ],
        },
    )

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="audit-layout", code_path=code, layout_context=layout_context), dest)

    root_context = read_json(dest / "layout_context.json")
    assert [item["path"] for item in root_context["active_visible_objects"]] == ["mobjects.11", "mobjects.13"]
    assert root_context["top_blocking_issues"][0]["a"]["path"] == "mobjects.11"
    assert read_json(dest / "facts" / "protected.json")["protect_string_literals"] is True


def test_build_workdir_compacts_layout_ticket_object_issues(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("print('layout')\n", encoding="utf-8")
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "top_blocking_issues": [
                {
                    "category": "text_formula_overlap",
                    "ratio_of_smaller": 1.0,
                    "a": {
                        "class": "MathTex",
                        "kind": "formula",
                        "text": "\\min(PD + PQ) = DQ",
                        "path": "mobjects.42",
                        "parent_path": "mobjects",
                        "bbox": {"left": 1.0522, "right": 4.0314, "center_x": 2.5418, "center_y": -0.3624},
                    },
                    "b": {
                        "class": "Text",
                        "kind": "text",
                        "text": "∴ △DCB 是等边三角形",
                        "path": "mobjects.46",
                        "parent_path": "mobjects",
                        "bbox": {"left": 1.05, "right": 5.1063, "center_x": 3.0781, "center_y": -0.3547},
                    },
                }
            ]
        },
    )

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="compact-layout", code_path=code, layout_context=layout_context), dest)

    serialized = json.dumps(read_json(dest / "layout_context.json"), ensure_ascii=False)
    assert "\\min(PD + PQ) = DQ" in serialized
    assert "∴ △DCB 是等边三角形" in serialized
    assert "mobjects.42" in serialized
    assert "parent_path" not in serialized
    assert not (dest / "TICKET.md").exists()


def test_build_workdir_writes_audit_compatible_root_layout_context_for_agent(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("print('layout')\n", encoding="utf-8")
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "safe_area": {"x_min": -7.1, "x_max": 7.1, "y_min": -4.0, "y_max": 4.0},
            "active_visible_objects": [
                {"path": "mobjects.1", "class": "MathTex", "kind": "formula", "text": "P", "parent_path": "mobjects", "bbox": {"left": 1, "right": 2, "top": 1, "bottom": 0, "center_x": 1.5}},
                {"path": "mobjects.2", "class": "Polygon", "kind": "shape", "parent_path": "mobjects", "bbox": {"left": 1, "right": 3, "top": 2, "bottom": -1, "center_x": 2}},
                {"path": "mobjects.unrelated", "class": "Text", "kind": "text", "text": "unrelated object that should not be sent to the agent"},
            ],
            "top_blocking_issues": [{"category": "label_shape_overlap_risk", "a": {"path": "mobjects.1", "text": "P"}, "b": {"path": "mobjects.2"}}],
        },
    )

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="compact-root", code_path=code, layout_context=layout_context), dest)

    root_context = read_json(dest / "layout_context.json")
    serialized = json.dumps(root_context, ensure_ascii=False)
    assert root_context["blocking_layout_issue_count"] == 1
    assert root_context["top_blocking_issues"][0]["a"]["path"] == "mobjects.1"
    assert "mobjects.unrelated" in serialized
    assert "parent_path" not in serialized
    assert len(serialized.encode("utf-8")) < 1600


def test_build_workdir_layout_brief_detects_step_panel_lifecycle(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("print('layout')\n", encoding="utf-8")
    issues = []
    for index, step in enumerate([12, 18, 24, 30, 36, 42], 1):
        issues.append(
            {
                "category": "text_formula_overlap",
                "step": step,
                "ratio_of_smaller": 0.9,
                "a": {
                    "path": f"mobjects.{index}",
                    "class": "Text",
                    "kind": "text",
                    "text": f"步骤 {index}",
                    "bbox": {"center_x": 2.5, "center_y": 0.5 - index * 0.05},
                },
                "b": {
                    "path": f"mobjects.{index + 20}",
                    "class": "MathTex",
                    "kind": "formula",
                    "text": f"x_{index}=y_{index}",
                    "bbox": {"center_x": 2.7, "center_y": 0.45 - index * 0.05},
                },
            }
        )
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "status": "layout_failed",
            "pass": False,
            "blocking_layout_issue_count": len(issues),
            "top_blocking_issues": issues,
        },
    )

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="brief-layout", code_path=code, layout_context=layout_context), dest)

    brief = read_json(dest / "layout_repair_brief.json")
    contract = read_json(dest / "layout_repair_contract.json")
    digest = read_json(dest / "layout_issue_digest.json")
    assert brief["summary"]["primary_failure_type"] == "step_panel_lifecycle_accumulation"
    assert brief["clusters"][0]["confidence"] >= 0.7
    assert "旧面板" in brief["clusters"][0]["root_cause"]
    assert "evidence" not in json.dumps(contract, ensure_ascii=False)
    assert digest["schema_version"] == "quality_repair.layout_issue_digest.issue_only.v1"
    assert digest["issue_count"] == len(issues)
    assert len(digest["issues"]) == len(issues)
    assert digest["issues"][-1]["issue_id"] == f"I{len(issues):03d}"
    assert digest["issues"][-1]["a"]["text"] == f"步骤 {len(issues)}"
    assert "issue_index" not in digest


def test_build_workdir_layout_brief_prioritizes_dominant_lifecycle_over_label_noise(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("print('layout')\n", encoding="utf-8")
    issues = []
    for index in range(1, 8):
        issues.append(
            {
                "category": "label_shape_overlap_risk",
                "step": 60 + index,
                "ratio_of_smaller": 1.0,
                "a": {
                    "path": f"mobjects.label.{index}",
                    "class": "Text",
                    "kind": "text",
                    "text": "35°",
                    "bbox": {"center_x": 2.5, "center_y": -0.4},
                },
                "b": {
                    "path": f"mobjects.line.{index}",
                    "class": "Line",
                    "kind": "shape",
                    "bbox": {"center_x": 2.4, "center_y": -0.4},
                },
            }
        )
    for index, step in enumerate(range(12, 92, 4), 1):
        issues.append(
            {
                "category": "text_formula_overlap",
                "step": step,
                "ratio_of_smaller": 0.55,
                "a": {
                    "path": f"mobjects.text.{index}",
                    "class": "Text",
                    "kind": "text",
                    "text": f"步骤 {index}",
                    "bbox": {"center_x": 2.4, "center_y": 0.6 - index * 0.04},
                },
                "b": {
                    "path": f"mobjects.formula.{index}",
                    "class": "MathTex",
                    "kind": "formula",
                    "text": f"x_{index}=y_{index}",
                    "bbox": {"center_x": 2.6, "center_y": 0.58 - index * 0.04},
                },
            }
        )
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "status": "layout_failed",
            "pass": False,
            "blocking_layout_issue_count": len(issues),
            "top_blocking_issues": issues,
        },
    )

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="dominant-lifecycle", code_path=code, layout_context=layout_context), dest)

    brief = read_json(dest / "layout_repair_brief.json")
    contract = read_json(dest / "layout_repair_contract.json")

    assert brief["summary"]["primary_failure_type"] == "step_panel_lifecycle_accumulation"
    assert brief["ignored_issue_count"] == 7
    assert brief["clusters"][0]["issue_count"] == 20
    assert contract["active_cluster_policy"]["primary_cluster_id"] == "C01"


def test_build_workdir_does_not_write_candidate_anchor_windows(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text(
        "class Scene_Anchor:\n"
        "    def make_problem_panel(self):\n"
        "        problem_panel = VGroup(Text('题目'), MathTex(\"35^\\\\circ\"))\n"
        "        return problem_panel\n"
        "\n"
        "    def place_panel(self, panel):\n"
        "        return panel.to_edge(RIGHT)\n"
        "\n"
        "    def construct(self):\n"
        "        step_panel = self.make_problem_panel()\n"
        "        self.place_panel(step_panel)\n"
        + "\n",
        encoding="utf-8",
    )
    layout_context = tmp_path / "layout_context.json"
    _write_json(
        layout_context,
        {
            "status": "layout_failed",
            "pass": False,
            "blocking_layout_issue_count": 1,
            "active_visible_objects": [
                {"name": "problem_panel", "class": "VGroup", "kind": "panel"},
                {"name": "step_panel", "class": "VGroup", "kind": "panel"},
            ],
            "top_blocking_issues": [
                {
                    "category": "text_formula_overlap",
                    "step": 12,
                    "ratio_of_smaller": 0.92,
                    "a": {
                        "name": "problem_panel",
                        "class": "MathTex",
                        "kind": "formula",
                        "text": "35°",
                        "bbox": {"center_x": 2.6, "center_y": 0.3},
                    },
                    "b": {
                        "name": "step_panel",
                        "class": "Text",
                        "kind": "text",
                        "text": "步骤 1",
                        "bbox": {"center_x": 2.7, "center_y": 0.32},
                    },
                }
            ],
        },
    )

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="anchor-layout", code_path=code, layout_context=layout_context), dest)

    digest = read_json(dest / "layout_issue_digest.json")
    assert digest["schema_version"] == "quality_repair.layout_issue_digest.issue_only.v1"
    assert digest["issue_count"] == 1
    assert digest["issues"][0]["a"]["name"] == "problem_panel"
    assert (dest / "candidate.py").exists()
    assert not (dest / "candidate_anchor_windows.md").exists()
