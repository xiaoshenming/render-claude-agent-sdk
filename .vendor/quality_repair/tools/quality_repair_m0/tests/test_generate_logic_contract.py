import json
import subprocess
import sys
from pathlib import Path

from libs.quality_repair.semantic_contract import generate_logic_contract


LOGIC_CHECK = Path(__file__).resolve().parents[2] / "quality_repair_checkers" / "logic_contract_check.py"


def test_generate_four_point_linear_contract_and_latex_escape_finding(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
class Solution:
    def make_point_by_coord(self, x, y): ...
    def construct(self):
        problem_panel = self.make_problem_panel([
            "在平面直角坐标系中有两点 A(-2, 2), B(1, 4)",
            "(1)在 x 轴上找点 P，使得 PA+PB 最小，则 P 坐标为；",
            "(2)在 y 轴上找点 P，使得 PA+PB 最小，则 P 坐标为；",
            "(3)在 x 轴上找点 P，使得 |PA-PB| 最大，则 P 坐标为；",
            "(4)在 y 轴上找点 P，使得 |PA-PB| 最大，则 P 坐标为。"
        ])
        dot_P1 = self.make_point_by_coord(-1, 0)
        dot_P2 = self.make_point_by_coord(0, 10/3)
        dot_P3 = self.make_point_by_coord(-5, 0)
        dot_P4 = self.make_point_by_coord(0, 6)
        step_panel_3 = self.make_step_panel([
            "直线 AB 解析式为 y=\\dfrac{2}{3}x+\\dfrac{10}{3}",
        ])
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)

    assert result.logic_contract["contracts"][0]["kind"] == "no_unescaped_latex_command"
    assert result.logic_contract["contracts"][1:5] == [
        {"kind": "point_coordinate", "target": "dot_P1", "expected_coords": [-1.0, 0.0, 0.0], "label": "(1) x-axis PA+PB min"},
        {"kind": "point_coordinate", "target": "dot_P2", "expected_coords": [0.0, 10 / 3, 0.0], "label": "(2) y-axis PA+PB min"},
        {"kind": "point_coordinate", "target": "dot_P3", "expected_coords": [-5.0, 0.0, 0.0], "label": "(3) x-axis |PA-PB| max"},
        {"kind": "point_coordinate", "target": "dot_P4", "expected_coords": [0.0, 6.0, 0.0], "label": "(4) y-axis |PA-PB| max"},
    ]
    assert result.logic_contract["issues"][0]["kind"] == "unescaped_latex_command"
    assert result.findings[0]["kind"] == "unescaped_latex_command"

    workdir = tmp_path / "workdir"
    result.write_to(workdir)
    failed = _run_logic_check(code, workdir)
    assert failed["passed"] is False
    assert failed["issues"][0]["kind"] == "unescaped_latex_command"

    fixed = code.read_text(encoding="utf-8").replace('"直线 AB 解析式为 y=\\dfrac', 'r"直线 AB 解析式为 y=\\dfrac')
    code.write_text(fixed, encoding="utf-8")
    passed = _run_logic_check(code, workdir)
    assert passed["passed"] is True


def test_generate_quadrilateral_perimeter_contract(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
class Solution:
    def make_point_by_coord(self, x, y): ...
    def construct(self):
        problem_panel = self.make_problem_panel([
            "如图，点 A、B 的坐标分别是(1, 2)，(2, 1)，在 y 轴上找一点 C，",
            "在 x 轴上找一点 D，使四边形 ACDB 的周长最小，",
            "则 C 的坐标为 ______，D 的坐标为 ______，最小周长为 ______。"
        ])
        dot_C_opt = self.make_point_by_coord(0, 1)
        dot_D_opt = self.make_point_by_coord(1, 0)
        step_panel_final = self.make_step_panel([
            "填空答案：",
            "C 的坐标为 (0, 1)",
            "D 的坐标为 (1, 0)",
            self.make_formula_row("最小周长为", "4\\sqrt{2}")
        ])
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)

    assert result.logic_contract["contracts"] == [
        {"kind": "point_coordinate", "target": "dot_C_opt", "expected_coords": [0.0, 1.0, 0.0], "label": "C is A'B' intersection with y-axis"},
        {"kind": "point_coordinate", "target": "dot_D_opt", "expected_coords": [1.0, 0.0, 0.0], "label": "D is A'B' intersection with x-axis"},
        {"kind": "source_contains", "text": "4\\sqrt{2}", "label": "minimum perimeter"},
    ]
    assert "A'(-1,2)" in result.source_region


def test_generate_geometry_minimum_contract_and_lifecycle_finding(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
class Solution:
    def construct(self):
        problem_lines = [
            "在△ABC中，∠ABC为钝角，AB=2√2，∠BAC=45°",
            "∠BAC的平分线交BC于点D，M、N分别是AD和AB上的动点",
            "求BM+MN的最小值"
        ]
        geometry_all.add(region_ABM, region_ABpM)
        geometry_all.add(region_ABpN)
        step_panel5 = self.make_step_panel([
            "∴BM+MN的最小值为2"
        ])
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)

    assert result.logic_contract["contracts"] == [
        {"kind": "source_contains", "text": "最小值为2", "label": "BM+MN final minimum"},
        {"kind": "source_not_contains", "text": "6\\sqrt{3}", "label": "do not use task 06 answer"},
        {"kind": "source_not_contains", "text": "6√3", "label": "do not use task 06 answer"},
    ]
    assert any(item["kind"] == "geometry_lifecycle_risk" for item in result.findings)


def test_generate_geometry_semantic_claim_contracts(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
import numpy as np

class Solution:
    def construct(self):
        A = np.array([-2.6, -2.25, 0])
        B = np.array([1.95, -2.25, 0])
        D = np.array([2.104, -0.302, 0])
        edge_AB = Line(A, B)
        edge_AD = Line(A, D)
        A_scaled = edge_AB.get_start()
        B_scaled = edge_AB.get_end()
        D_scaled = edge_AD.get_end()
        problem_lines = ["M、N分别是AD和AB上的动点"]
        B_prime = np.array([-2.6, 0.75, 0])
        M_rand = (A_scaled + D_scaled) * 0.4 + A_scaled * 0.6
        N_rand = (A_scaled + B_scaled) * 0.3 + A_scaled * 0.7
        step_panel = self.make_step_panel([
            "B关于AD的对称点B'",
            "AD垂直平分BB'，∠AMB=∠AMB'=90°"
        ])
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)
    kinds = [item["kind"] for item in result.logic_contract["contracts"]]

    assert "point_on_line" in kinds
    assert "reflection_point" in kinds
    assert "angle_measure" in kinds
    assert kinds[0] == "point_on_line"
    assert any(item["kind"] == "point_not_on_claimed_line" for item in result.findings)
    assert any(item["kind"] == "reflection_point_mismatch" for item in result.findings)
    assert any(item["kind"] == "angle_measure_mismatch" for item in result.findings)
    assert "B_prime = np.array" in result.source_region
    assert "M_rand =" in result.source_region
    assert "N_rand =" in result.source_region
    assert "∠AMB=∠AMB'=90°" in result.source_region
    assert "suggested_replacement=M_rand = A_scaled * 0.6 + D_scaled * 0.4" in result.source_region
    assert "suggested_replacement=N_rand = A_scaled * 0.7 + B_scaled * 0.3" in result.source_region
    assert "suggested_replacement=B_prime = np.array" in result.source_region

    workdir = tmp_path / "workdir"
    result.write_to(workdir)
    failed = _run_logic_check(code, workdir)
    assert failed["passed"] is False
    issue_kinds = {item["kind"] for item in failed["issues"]}
    assert {"point_not_on_line", "reflection_point_wrong", "angle_measure_wrong"} <= issue_kinds


def test_generate_line_endpoint_contracts_from_named_line_variables(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
class Solution:
    def construct(self):
        dot_A = self.make_point_by_coord(1, 2)
        dot_C = self.make_point_by_coord(0, 2.5)
        dot_D = self.make_point_by_coord(3, 0)
        dot_B = self.make_point_by_coord(2, 1)
        line_AC = self.make_line_by_formula(-1.5, 2.5, x_range=[0, 1])
        line_CD = self.make_line_by_formula(-0.8333333333, 2.5, x_range=[0, 3])
        line_DB = self.make_line_by_formula(1, -3, x_range=[2, 3])
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)

    endpoint_contracts = [item for item in result.logic_contract["contracts"] if item["kind"] == "line_endpoint_match"]
    assert {item["target"] for item in endpoint_contracts} == {"line_AC", "line_DB"}
    assert any(item["kind"] == "line_endpoint_mismatch" and item["target"] == "line_AC" for item in result.findings)
    assert any(item["kind"] == "line_endpoint_mismatch" and item["target"] == "line_DB" for item in result.findings)
    assert "suggested_replacement=line_AC = self.make_line_by_formula(-0.5, 2.5, x_range=[0, 1])" in result.source_region
    assert "suggested_replacement=line_DB = self.make_line_by_formula(-1, 3, x_range=[2, 3])" in result.source_region
    assert "line_AC = self.make_line_by_formula" in result.source_region
    assert "line_DB = self.make_line_by_formula" in result.source_region

    workdir = tmp_path / "workdir"
    result.write_to(workdir)
    failed = _run_logic_check(code, workdir)
    assert failed["passed"] is False
    issue_kinds = {item["kind"] for item in failed["issues"]}
    assert "line_endpoint_mismatch" in issue_kinds

    fixed = code.read_text(encoding="utf-8").replace(
        "line_AC = self.make_line_by_formula(-1.5, 2.5, x_range=[0, 1])",
        "line_AC = self.make_line_by_formula(-0.5, 2.5, x_range=[0, 1])",
    ).replace(
        "line_DB = self.make_line_by_formula(1, -3, x_range=[2, 3])",
        "line_DB = self.make_line_by_formula(-1, 3, x_range=[2, 3])",
    )
    code.write_text(fixed, encoding="utf-8")
    passed = _run_logic_check(code, workdir)
    assert passed["passed"] is True


def test_empty_logic_contract_has_no_blocking_issue(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
class Solution:
    def construct(self):
        self.wait(0.1)
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)
    assert result.logic_contract["kind"] == "none"
    assert result.logic_contract["contracts"] == []

    workdir = tmp_path / "workdir"
    result.write_to(workdir)
    passed = _run_logic_check(code, workdir)
    assert passed["passed"] is True
    assert passed["blocking_count"] == 0


def test_generate_contract_cli_writes_bundle_files(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
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
    out_dir = tmp_path / "out"

    subprocess.run(
        [sys.executable, "tools/quality_repair_m0/generate_logic_contract.py", "--code", str(code), "--out", str(out_dir)],
        check=True,
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
    )

    payload = json.loads((out_dir / "logic_contract_context.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert len(payload["contracts"]) == 4
    assert (out_dir / "source_region.md").exists()
    assert (out_dir / "review_findings.json").exists()


def _run_logic_check(code: Path, workdir: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(LOGIC_CHECK), "--code", str(code), "--workdir", str(workdir)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)
