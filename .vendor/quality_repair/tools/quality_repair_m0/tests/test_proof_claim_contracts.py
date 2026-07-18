import json
import subprocess
import sys
from pathlib import Path

import pytest

from libs.quality_repair.semantic_contract import generate_logic_contract


LOGIC_CHECK = Path(__file__).resolve().parents[2] / "quality_repair_checkers" / "logic_contract_check.py"


def test_geometry_facts_extracts_points_affine_and_line_operations() -> None:
    source = '''
import numpy as np
class Solution:
    def construct(self):
        A = np.array([-2.6, -2.25, 0])
        B = np.array([1.95, -2.25, 0])
        C = np.array([2.34, 2.69, 0])
        D = np.array([2.104, -0.302, 0])
        B_prime = np.array([-2.6, 0.75, 0])
        M_rand = A * 0.6 + D * 0.4
        N_rand = A * 0.7 + B * 0.3
'''

    from libs.quality_repair.semantic_contract.geometry_facts import (
        angle_degrees,
        extract_geometry_facts,
        foot_point,
        line_intersection,
        point_line_distance,
    )

    facts = extract_geometry_facts(source)

    assert facts.points["A"] == (-2.6, -2.25, 0.0)
    assert facts.points["M_rand"] == pytest.approx((-0.7184, -1.4708, 0.0))
    assert point_line_distance(facts.points["M_rand"], facts.points["A"], facts.points["D"]) <= 1e-9
    assert round(angle_degrees(facts.points["B"], facts.points["A"], facts.points["C"]), 1) == 45.0
    foot = foot_point(facts.points["B_prime"], facts.points["A"], facts.points["B"])
    assert foot == (-2.6, -2.25, 0.0)
    intersection = line_intersection(facts.points["A"], facts.points["D"], facts.points["B_prime"], foot)
    assert intersection is not None


def test_extract_angle_length_collinear_and_perpendicular_claims() -> None:
    source = '''
class Solution:
    def construct(self):
        MathTex("\\\\therefore \\\\angle F = \\\\angle ACB = 35^\\\\circ")
        MathTex("\\\\therefore \\\\angle F = \\\\angle AEB \\\\implies BF = BE")
        with self.voiceover(text="当 B'、M、N 共线且 B'N 垂直于 AB 时，总长最小。"):
            pass
'''

    from libs.quality_repair.semantic_contract.proof_claims import extract_proof_claims

    claims = extract_proof_claims(source)
    kinds = [item.kind for item in claims]

    assert "angle_equals_degrees" in kinds
    assert "angle_equals_angle" in kinds
    assert "length_equals_length" in kinds
    assert "points_collinear" in kinds
    assert "line_perpendicular" in kinds


def test_extract_angle_degree_claim_keeps_unrelated_angles_separate() -> None:
    source = '''
class Solution:
    def construct(self):
        problem_lines = ["在△ABC中，∠ABC为钝角，AB=2√2，∠BAC=45°"]
'''

    from libs.quality_repair.semantic_contract.proof_claims import extract_proof_claims

    claims = extract_proof_claims(source)
    degree_claims = [item for item in claims if item.kind == "angle_equals_degrees"]
    equality_claims = [item for item in claims if item.kind == "angle_equals_angle"]

    assert [item.points for item in degree_claims] == [("B", "A", "C")]
    assert equality_claims == []


def test_extract_length_claim_ignores_sum_equations() -> None:
    source = '''
class Solution:
    def construct(self):
        MathTex("BE = AB + AD + BD")
        MathTex("\\\\therefore \\\\angle F = \\\\angle AEB \\\\implies BF = BE")
'''

    from libs.quality_repair.semantic_contract.proof_claims import extract_proof_claims

    claims = [item for item in extract_proof_claims(source) if item.kind == "length_equals_length"]

    assert [(item.segment_a, item.segment_b) for item in claims] == [(("B", "F"), ("B", "E"))]


def test_generate_reflection_shortest_path_contracts_for_task_07(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
import numpy as np
class Solution:
    def construct(self):
        A = np.array([-2.6, -2.25, 0])
        B = np.array([1.95, -2.25, 0])
        C = np.array([2.34, 2.69, 0])
        D = np.array([2.104, -0.302, 0])
        B_prime = np.array([-2.6, 0.75, 0])
        M_rand = A * 0.6 + D * 0.4
        N_rand = A * 0.7 + B * 0.3
        step = ["当B'、M、N共线且B'N⊥AB时，总长最小", "N是B'到AB的垂足", "M是AD与B'N的交点"]
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)
    kinds = [item["kind"] for item in result.logic_contract["contracts"]]

    assert "foot_point" in kinds
    assert "line_intersection" in kinds
    assert "points_collinear" in kinds
    assert "line_perpendicular" in kinds
    assert any("N_rand" in str(item.get("suggested_replacement")) for item in result.logic_contract["contracts"])

    workdir = tmp_path / "workdir"
    result.write_to(workdir)
    failed = _run_logic_check(code, workdir)
    issue_kinds = {item["kind"] for item in failed["issues"]}
    assert {"foot_point_wrong", "line_intersection_wrong", "points_not_collinear", "line_perpendicular_wrong"} <= issue_kinds


def test_generate_exterior_angle_proof_claim_mismatch_contracts(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
import numpy as np
class Solution:
    def construct(self):
        B = np.array([0.0, 0.0, 0.0])
        C = np.array([4.0, 0.0, 0.0])
        A = np.array([0.812, 2.23, 0.0])
        D = np.array([2.0, 1.4, 0.0])
        E = np.array([-6.26, 0.0, 0.0])
        F = np.array([1.55, 4.1, 0.0])
        MathTex("\\\\therefore \\\\angle F = \\\\angle ACB = 35^\\\\circ")
        MathTex("\\\\therefore \\\\angle F = \\\\angle AEB \\\\implies BF = BE")
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)
    kinds = [item["kind"] for item in result.logic_contract["contracts"]]

    assert "angle_equals_degrees" in kinds
    assert "angle_equals_angle" in kinds
    assert "length_equals_length" in kinds
    assert any(item["kind"] == "angle_claim_mismatch" for item in result.findings)
    assert any(item["kind"] == "length_claim_mismatch" for item in result.findings)

    workdir = tmp_path / "workdir"
    result.write_to(workdir)
    failed = _run_logic_check(code, workdir)
    issue_kinds = {item["kind"] for item in failed["issues"]}
    assert {"angle_equals_degrees_wrong", "angle_equals_angle_wrong", "length_equals_length_wrong"} <= issue_kinds


def test_generate_exterior_angle_claims_resolve_pt_prefixed_points(tmp_path: Path) -> None:
    code = tmp_path / "candidate.py"
    code.write_text(
        '''
import numpy as np
class Solution:
    def construct(self):
        pt_A = np.array([0.812, 2.23, 0.0])
        pt_B = np.array([0.0, 0.0, 0.0])
        pt_C = np.array([4.0, 0.0, 0.0])
        pt_E = np.array([-6.26, 0.0, 0.0])
        vec_BA = pt_A - pt_B
        unit_BA = vec_BA / np.linalg.norm(vec_BA)
        pt_F = pt_A + 1.4 * unit_BA
        MathTex("\\\\text{易证 } \\\\angle F = \\\\angle ACB = 35^\\\\circ \\\\text{，} \\\\angle AEB = 35^\\\\circ")
''',
        encoding="utf-8",
    )

    result = generate_logic_contract(code)
    contracts = result.logic_contract["contracts"]

    assert any(item["kind"] == "angle_equals_angle" and item["points"] == ["pt_A", "pt_F", "pt_E"] for item in contracts)
    assert any(item["kind"] == "angle_equals_degrees" and item["points"] == ["pt_A", "pt_F", "pt_E"] for item in contracts)


def _run_logic_check(code: Path, workdir: Path) -> dict:
    result = subprocess.run(
        [sys.executable, str(LOGIC_CHECK), "--code", str(code), "--workdir", str(workdir)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)
