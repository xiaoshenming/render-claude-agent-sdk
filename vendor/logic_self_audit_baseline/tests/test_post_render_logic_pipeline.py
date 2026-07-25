import asyncio

from app.workers.post_render_logic.evidence import build_logic_evidence
from app.workers.post_render_logic.orchestrator import LogicRepairOrchestrator
from app.workers.post_render_logic.planning import plan_repairs
from app.workers.post_render_logic.recheck import recheck_issues
from app.workers.post_render_logic.schemas import LogicIssue, ReviewReport
from app.workers.post_render_logic.scene_patch import apply_scene_replacements


SAMPLE_CODE = """
from manim import *

class Scene_01_Intro(Scene):
    def construct(self):
        title = Text("题目：求 x 的值")
        self.add(title)

class Scene_02_Solve(Scene):
    def construct(self):
        answer = MathTex("x=12")
        note = Text("所以最终答案是 x=12")
        self.add(answer, note)
"""


def test_build_logic_evidence_extracts_scene_digest_without_render_concerns():
    evidence = build_logic_evidence(
        code=SAMPLE_CODE,
        job_id="job-001",
        problem_text="求 x 的值，标准答案是 x=10",
        expected_answer="x=10",
    )

    assert evidence.job_id == "job-001"
    assert evidence.problem_text.startswith("求 x")
    assert [scene.scene_id for scene in evidence.scenes] == [
        "Scene_01_Intro",
        "Scene_02_Solve",
    ]
    assert evidence.scenes[1].formulas == ["x=12"]
    assert "所以最终答案是 x=12" in evidence.scenes[1].texts
    assert evidence.source_code_hash.startswith("sha256:")


def test_plan_repairs_freezes_scope_and_allows_only_repairable_single_scene_issue():
    issue = LogicIssue(
        issue_id="ISSUE-001",
        issue_type="final_answer_mismatch",
        severity="high",
        confidence=0.92,
        repairable=True,
        repair_scope="formula_claim_only",
        target_scene_ids=["Scene_02_Solve"],
        evidence=[{"artifact": "scene_code", "claim": "MathTex('x=12')"}],
        expected="x=10",
        observed="x=12",
        acceptance_predicates=[
            {
                "predicate": "text_absent",
                "value": "x=12",
                "scene_id": "Scene_02_Solve",
            },
            {
                "predicate": "text_present",
                "value": "x=10",
                "scene_id": "Scene_02_Solve",
            },
        ],
    )

    plan = plan_repairs([issue])

    assert plan.issue_ids == ["ISSUE-001"]
    assert plan.target_scene_ids == ["Scene_02_Solve"]
    assert plan.max_coder_attempts == 1
    assert "no BaseConfigScene/header/helper edits" in plan.forbidden_changes
    assert plan.acceptance_predicates == issue.acceptance_predicates


def test_apply_scene_replacements_touches_only_target_scene_and_reports_claims():
    fixed_code, attempt = apply_scene_replacements(
        code=SAMPLE_CODE,
        replacements={"Scene_02_Solve": {"x=12": "x=10"}},
        plan_id="repair-plan-001",
        issue_ids=["ISSUE-001"],
    )

    assert "Scene_01_Intro" in fixed_code
    assert "x=10" in fixed_code
    assert "x=12" not in fixed_code
    assert attempt.touched_regions == [
        {
            "artifact": "scene_code",
            "scene_id": "Scene_02_Solve",
            "symbol": "class_body",
        }
    ]
    assert attempt.changed_claims == [
        {
            "before": "x=12",
            "after": "x=10",
            "linked_issue_id": "ISSUE-001",
        }
    ]


def test_recheck_only_evaluates_frozen_acceptance_predicates():
    fixed_code = SAMPLE_CODE.replace("x=12", "x=10")
    issue = LogicIssue(
        issue_id="ISSUE-001",
        issue_type="final_answer_mismatch",
        severity="high",
        confidence=0.92,
        repairable=True,
        repair_scope="formula_claim_only",
        target_scene_ids=["Scene_02_Solve"],
        evidence=[],
        expected="x=10",
        observed="x=12",
        acceptance_predicates=[
            {
                "predicate": "text_absent",
                "value": "x=12",
                "scene_id": "Scene_02_Solve",
            },
            {
                "predicate": "text_present",
                "value": "x=10",
                "scene_id": "Scene_02_Solve",
            },
        ],
    )

    result = recheck_issues(fixed_code, [issue])

    assert result.new_issue_scan == "disabled"
    assert result.final_decision == "accept_repair"
    assert result.results[0]["status"] == "fixed"
    assert {item["predicate"] for item in result.results[0]["predicate_results"]} == {
        "text_absent",
        "text_present",
    }


def test_orchestrator_uses_review_plan_patch_recheck_without_recursive_review():
    class FakeReviewer:
        calls = 0

        async def review(self, evidence):
            self.calls += 1
            return ReviewReport(
                review_id="logic-review-001",
                source_code_hash=evidence.source_code_hash,
                decision="repair",
                issues=[
                    LogicIssue(
                        issue_id="ISSUE-001",
                        issue_type="final_answer_mismatch",
                        severity="high",
                        confidence=0.95,
                        repairable=True,
                        repair_scope="formula_claim_only",
                        target_scene_ids=["Scene_02_Solve"],
                        evidence=[],
                        expected="x=10",
                        observed="x=12",
                        acceptance_predicates=[
                            {
                                "predicate": "text_absent",
                                "value": "x=12",
                                "scene_id": "Scene_02_Solve",
                            },
                            {
                                "predicate": "text_present",
                                "value": "x=10",
                                "scene_id": "Scene_02_Solve",
                            },
                        ],
                    )
                ],
            )

    class FakeCoder:
        async def patch(self, code, plan):
            return apply_scene_replacements(
                code=code,
                replacements={"Scene_02_Solve": {"x=12": "x=10"}},
                plan_id=plan.plan_id,
                issue_ids=plan.issue_ids,
            )

    reviewer = FakeReviewer()
    orchestrator = LogicRepairOrchestrator(
        reviewer=reviewer,
        coder=FakeCoder(),
        render_again=lambda code: True,
    )

    result = asyncio.run(
        orchestrator.run(
            code=SAMPLE_CODE,
            job_id="job-001",
            problem_text="求 x 的值，标准答案是 x=10",
            expected_answer="x=10",
        )
    )

    assert reviewer.calls == 1
    assert result.state == "FIXED"
    assert result.recheck.final_decision == "accept_repair"
    assert result.fixed_code is not None
