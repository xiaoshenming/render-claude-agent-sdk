import json
from pathlib import Path

from libs.quality_repair import RepairBundle
from libs.quality_repair.contract import build_workdir
from libs.quality_repair.schemas import PROFILE_LOGIC, read_json


def test_build_workdir_logic_bundle_places_contract_and_source_region(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("class Scene_02:\n    pass\n", encoding="utf-8")
    logic_contract = tmp_path / "logic_contract_context.json"
    logic_contract.write_text(json.dumps({"issues": [{"kind": "value_mismatch", "a": "P", "b": "Q"}]}, ensure_ascii=False), encoding="utf-8")
    source_region = tmp_path / "source_region.md"
    source_region.write_text("# 出错源码区域\n\n第 12-18 行\n", encoding="utf-8")

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="job-3", code_path=code, profile=PROFILE_LOGIC, logic_contract=logic_contract, source_region=source_region), dest)

    assert read_json(dest / "facts" / "logic_contract.json")["issues"][0]["kind"] == "value_mismatch"
    protected = read_json(dest / "facts" / "protected.json")
    assert protected["protect_string_literals"] is False
    assert "max_edit_calls" not in protected
    assert (dest / "facts" / "source_region.md").read_text(encoding="utf-8") == source_region.read_text(encoding="utf-8")
    ticket = (dest / "TICKET.md").read_text(encoding="utf-8")
    assert "profile: logic" in ticket
    assert "问题条数: 1" in ticket
    assert "可多次 Edit" in ticket
    assert "清零合同阻断" in ticket
    assert not (dest / "build_warnings.json").exists()


def test_build_workdir_logic_bundle_auto_generates_contract(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text(
        '''
class Solution:
    def make_point_by_coord(self, x, y): ...
    def construct(self):
        problem_panel = self.make_problem_panel(["在平面直角坐标系中有两点 A(-2, 2), B(1, 4)"])
        dot_P1 = self.make_point_by_coord(-1, 0)
        dot_P2 = self.make_point_by_coord(0, 10/3)
        dot_P3 = self.make_point_by_coord(-5, 0)
        dot_P4 = self.make_point_by_coord(0, 6)
''',
        encoding="utf-8",
    )
    dest = tmp_path / "workdir"

    build_workdir(RepairBundle(job_id="auto-logic", code_path=code, profile=PROFILE_LOGIC), dest)

    facts = read_json(dest / "facts" / "logic_contract.json")
    assert facts["kind"] == "point_coordinate"
    assert facts["target"] == "dot_P1"
    assert facts["expected_coords"] == [-1.0, 0.0, 0.0]
    assert (dest / "facts" / "source_region.md").read_text(encoding="utf-8").strip()
    warnings = read_json(dest / "build_warnings.json")["warnings"]
    assert "logic_contract_auto_generated" in warnings
    assert "logic_contract_not_provided" not in warnings
    assert "source_region_not_provided" not in warnings


def test_build_workdir_normalizes_audit_logic_contract_context(tmp_path: Path) -> None:
    code = tmp_path / "candidate_src.py"
    code.write_text("print('logic')\n", encoding="utf-8")
    logic_contract = tmp_path / "logic_contract_context.json"
    logic_contract.write_text(
        json.dumps(
            {
                "contracts": [{"kind": "equal_length", "segment_a": ["p1", "p2"], "segment_b": ["p3", "p4"], "move_point": "p4"}],
                "before_validation": {
                    "issues": [
                        {
                            "kind": "equal_length_wrong",
                            "target": "p4",
                            "evidence": {
                                "expected_coords": [3.8671603823699967, -1.8531358470520014, 0.0],
                                "actual_coords": [4.0, -1.8, 0.0],
                                "reference_length": 2.5495097567963922,
                                "actual_length": 2.692582403567252,
                            },
                        }
                    ]
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    source_region = tmp_path / "source_region.md"
    source_region.write_text("raw source region\n", encoding="utf-8")

    dest = tmp_path / "workdir"
    build_workdir(RepairBundle(job_id="audit-logic", code_path=code, profile=PROFILE_LOGIC, logic_contract=logic_contract, source_region=source_region), dest)

    facts = read_json(dest / "facts" / "logic_contract.json")
    assert facts["kind"] == "equal_length"
    assert facts["target"] == "p4"
    assert facts["expected_coords"] == [3.8671603823699967, -1.8531358470520014, 0.0]
    assert facts["actual_coords"] == [4.0, -1.8, 0.0]
    assert facts["expected_length"] == 2.5495097567963922
    assert facts["actual_length"] == 2.692582403567252
    assert facts["issues"][0]["kind"] == "equal_length_wrong"
    assert read_json(dest / "logic_contract_context.json")["contracts"][0]["kind"] == "equal_length"
    assert (dest / "source_region.md").read_text(encoding="utf-8") == "raw source region\n"
