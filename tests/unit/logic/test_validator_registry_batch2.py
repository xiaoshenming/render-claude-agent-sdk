
from manim_quality.logic._scene_evidence import extract_scenes

from manim_quality.logic.diff_guard import evaluate_logic_diff

from manim_quality.logic.repair_plan import EditRegion, RepairPlan

from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicIssue,
)

from manim_quality.logic.validators.registry import ValidationStatus, validate_candidate

from manim_quality.revisions.fingerprint import code_hash, sha256_text

BEFORE = """from manim import *

class Demo(Scene):
    def construct(self):
        answer = MathTex("x=12")
        self.add(answer)
"""

def issue(predicates: tuple[dict[str, object], ...]) -> LogicIssue:
    return LogicIssue(
        issue_id="I-1",
        issue_type="answer_mismatch",
        severity=IssueSeverity.HIGH,
        confidence=0.95,
        repairable=True,
        repair_scope="minimal scene-local correction",
        target_scene_ids=("Demo",),
        evidence=(
            EvidenceCitation(
                CitationArtifact.CANDIDATE_CODE,
                "candidate.py",
                code_hash(BEFORE),
                'answer = MathTex("x=12")',
                "Demo",
                5,
                5,
            ),
            EvidenceCitation(
                CitationArtifact.EXPECTED_ANSWER,
                "expected.txt",
                sha256_text("x=10"),
                "x=10",
            ),
        ),
        expected="x=10",
        observed="x=12",
        acceptance_predicates=predicates,
        non_goals=("layout",),
    )

def plan(issues: tuple[LogicIssue, ...]) -> RepairPlan:
    scene = extract_scenes(BEFORE)[0]
    return RepairPlan(
        "plan-1",
        code_hash(BEFORE),
        issues,
        ("Demo",),
        (EditRegion("Demo", scene.line_start, scene.line_end),),
        ("layout",),
    )

def test_registry_confirms_targeted_geometry_mismatch_was_removed() -> None:
    before = """from manim import *

class Demo(Scene):
    def construct(self):
        point_A = make_point_by_coord(0, 0)
        point_B = make_point_by_coord(2, 2)
        line_AB = make_line_by_formula(0, 0, x_range=[0, 2])
        self.add(line_AB)
"""
    after = before.replace("make_line_by_formula(0, 0", "make_line_by_formula(1, 0")
    line = 7
    geometry_issue = LogicIssue(
        "G-1",
        "line_endpoint_formula_mismatch",
        IssueSeverity.HIGH,
        1.0,
        True,
        "repair the cited Scene line",
        ("Demo",),
        (
            EvidenceCitation(
                CitationArtifact.CANDIDATE_CODE,
                "candidate.py",
                code_hash(before),
                before.splitlines()[line - 1].strip(),
                "Demo",
                line,
                line,
            ),
            EvidenceCitation(
                CitationArtifact.PROBLEM_TEXT,
                "problem.txt",
                sha256_text("AB joins A and B"),
                "AB joins A and B",
            ),
        ),
        "line endpoints match A and B",
        "line endpoints do not match A and B",
        ({"reason": "formula endpoints must match the cited points"},),
        ("layout",),
    )
    scene = extract_scenes(before)[0]
    repair_plan = RepairPlan(
        "plan-target-geometry",
        code_hash(before),
        (geometry_issue,),
        ("Demo",),
        (EditRegion("Demo", scene.line_start, scene.line_end),),
        ("layout",),
    )

    report = validate_candidate(
        before,
        after,
        repair_plan,
        evaluate_logic_diff(before, after, repair_plan),
    )

    targeted = next(
        check for check in report.checks if check.validator == "geometry_resolution"
    )
    assert targeted.status is ValidationStatus.PASS
    assert targeted.issue_id == "G-1"

def test_geometry_resolution_rejects_renamed_equivalent_mismatch() -> None:
    before = """from manim import *

class Demo(Scene):
    def construct(self):
        point_A = make_point_by_coord(0, 0)
        point_B = make_point_by_coord(2, 2)
        line_AB = make_line_by_formula(0, 0, x_range=[0, 2])
        self.add(line_AB)
"""
    after = before.replace("point_A", "point_C").replace("point_B", "point_D")
    after = after.replace("line_AB", "line_CD")
    line = 7
    geometry_issue = LogicIssue(
        "G-rename",
        "line_endpoint_formula_mismatch",
        IssueSeverity.HIGH,
        1.0,
        True,
        "repair the cited geometry",
        ("Demo",),
        (
            EvidenceCitation(
                CitationArtifact.CANDIDATE_CODE,
                "candidate.py",
                code_hash(before),
                before.splitlines()[line - 1].strip(),
                "Demo",
                line,
                line,
            ),
            EvidenceCitation(
                CitationArtifact.PROBLEM_TEXT,
                "problem.txt",
                sha256_text("AB must join its endpoints"),
                "AB must join its endpoints",
            ),
        ),
        "line joins its endpoints",
        "line misses its endpoints",
        ({"reason": "line must match its endpoint coordinates"},),
        ("layout",),
    )
    scene = extract_scenes(before)[0]
    repair_plan = RepairPlan(
        "plan-renamed-geometry",
        code_hash(before),
        (geometry_issue,),
        ("Demo",),
        (EditRegion("Demo", scene.line_start, scene.line_end),),
        ("layout",),
    )

    report = validate_candidate(
        before,
        after,
        repair_plan,
        evaluate_logic_diff(before, after, repair_plan),
    )

    targeted = next(
        check for check in report.checks if check.validator == "geometry_resolution"
    )
    assert targeted.status is ValidationStatus.FAIL
