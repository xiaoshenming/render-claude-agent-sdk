import asyncio

from app.workers.post_render_logic.claude_adapters import (
    ClaudeLogicReviewer,
    ClaudeSceneCoder,
)
from app.workers.post_render_logic.evidence import build_logic_evidence
from app.workers.post_render_logic.factory import build_claude_logic_orchestrator
from app.workers.post_render_logic.planning import plan_repairs
from app.workers.post_render_logic.sdk_runner import ClaudeAgentJsonRunner
from app.workers.post_render_logic.schemas import LogicIssue


SAMPLE_CODE = """
from manim import *

class Scene_02_Solve(Scene):
    def construct(self):
        answer = MathTex("x=12")
        note = Text("所以最终答案是 x=12")
        self.add(answer, note)
"""


class FakeJsonRunner:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def run_json(self, *, prompt, schema, system_prompt):
        self.calls.append(
            {
                "prompt": prompt,
                "schema": schema,
                "system_prompt": system_prompt,
            }
        )
        return self.payload


def test_claude_logic_reviewer_converts_sdk_json_to_review_report():
    evidence = build_logic_evidence(
        code=SAMPLE_CODE,
        job_id="job-001",
        problem_text="求 x 的值，标准答案是 x=10",
        expected_answer="x=10",
    )
    runner = FakeJsonRunner(
        {
            "review_id": "logic-review-001",
            "decision": "repair",
            "blocked": False,
            "issues": [
                {
                    "issue_id": "ISSUE-001",
                    "issue_type": "final_answer_mismatch",
                    "severity": "high",
                    "confidence": 0.95,
                    "repairable": True,
                    "repair_scope": "formula_claim_only",
                    "target_scene_ids": ["Scene_02_Solve"],
                    "evidence": [
                        {
                            "artifact": "scene_code",
                            "claim": "MathTex('x=12') conflicts with expected x=10",
                        }
                    ],
                    "expected": "x=10",
                    "observed": "x=12",
                    "acceptance_predicates": [
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
                    "non_goals": ["do not inspect layout"],
                }
            ],
        }
    )

    report = asyncio.run(ClaudeLogicReviewer(runner).review(evidence))

    assert report.decision == "repair"
    assert report.source_code_hash == evidence.source_code_hash
    assert report.issues[0].issue_id == "ISSUE-001"
    assert "不做视觉" in runner.calls[0]["system_prompt"]
    assert runner.calls[0]["schema"]["type"] == "object"


def test_claude_scene_coder_applies_sdk_replacements_inside_planned_scene_only():
    issue = LogicIssue(
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
        acceptance_predicates=[],
    )
    plan = plan_repairs([issue])
    runner = FakeJsonRunner(
        {
            "replacements": {
                "Scene_02_Solve": {
                    "x=12": "x=10",
                }
            },
            "risk_flags": [],
        }
    )

    fixed_code, attempt = asyncio.run(ClaudeSceneCoder(runner).patch(SAMPLE_CODE, plan))

    assert "x=10" in fixed_code
    assert "x=12" not in fixed_code
    assert attempt.plan_id == plan.plan_id
    assert attempt.changed_claims[0]["linked_issue_id"] == "ISSUE-001"
    assert "只允许返回 replacements" in runner.calls[0]["system_prompt"]


def test_claude_agent_json_runner_extracts_structured_output_from_sdk_result():
    class FakeResult:
        structured_output = {"decision": "pass", "issues": []}

    async def fake_query(**kwargs):
        fake_query.last_options = kwargs["options"]
        yield FakeResult()

    runner = ClaudeAgentJsonRunner(query_func=fake_query, cwd=".")
    result = asyncio.run(
        runner.run_json(
            prompt="review",
            schema={"type": "object"},
            system_prompt="system",
        )
    )

    assert result == {"decision": "pass", "issues": []}
    assert fake_query.last_options.output_format == {
        "type": "json_schema",
        "schema": {"type": "object"},
    }
    assert fake_query.last_options.permission_mode == "dontAsk"
    assert fake_query.last_options.tools == []
    assert fake_query.last_options.allowed_tools == []
    assert fake_query.last_options.disallowed_tools == []


def test_claude_agent_json_runner_parses_json_result_text_when_needed():
    class FakeResult:
        structured_output = None
        result = '{"replacements":{"Scene_02_Solve":{"x=12":"x=10"}}}'

    async def fake_query(**kwargs):
        yield FakeResult()

    runner = ClaudeAgentJsonRunner(query_func=fake_query, cwd=".")
    result = asyncio.run(
        runner.run_json(
            prompt="patch",
            schema={"type": "object"},
            system_prompt="system",
        )
    )

    assert result["replacements"]["Scene_02_Solve"]["x=12"] == "x=10"


def test_factory_builds_claude_sdk_orchestrator_with_shared_runner():
    orchestrator = build_claude_logic_orchestrator(
        render_again=lambda code: True,
        cwd=".",
        model="claude-sonnet-4-5",
    )

    assert isinstance(orchestrator.reviewer, ClaudeLogicReviewer)
    assert isinstance(orchestrator.coder, ClaudeSceneCoder)
    assert orchestrator.reviewer.runner is orchestrator.coder.runner
    assert orchestrator.reviewer.runner.model == "claude-sonnet-4-5"
