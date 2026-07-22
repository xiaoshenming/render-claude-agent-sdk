from pathlib import Path

import pytest

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.profile import verifier_profile
from manim_quality.agents.runtime import (
    AgentRuntime,
    BackendRequest,
    BackendResult,
    RuntimeControls,
)
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink
from manim_quality.logic._scene_evidence import extract_scenes
from manim_quality.logic._verifier_evidence import bind_candidate_evidence
from manim_quality.logic.diff_guard import evaluate_logic_diff
from manim_quality.logic.repair_plan import EditRegion, RepairPlan
from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicIssue,
)
from manim_quality.logic.validators.registry import validate_candidate
from manim_quality.logic.verifier import DirectedVerifier, DirectedVerifierError
from manim_quality.revisions.fingerprint import code_hash, sha256_text

BEFORE = """from manim import *

class Demo(Scene):
    def construct(self):
        answer = MathTex("x=12")
        self.add(answer)
"""
AFTER = BEFORE.replace("x=12", "x=10")


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class VerifierBackend:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.request: BackendRequest | None = None

    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        self.request = request
        controls.record_round_usage(TokenUsage(input_tokens=20, output_tokens=10))
        controls.authorize_tool("Read", {"file_path": request.readable_paths[0]})
        controls.authorize_output_submission(self.payload)
        return controls.complete(self.payload)


def limits() -> BudgetLimits:
    return BudgetLimits(100_000, 2, 3, 10_000, 2_000, 1_000, 1_000, 1_000, 4_000)


def issue() -> LogicIssue:
    return LogicIssue(
        "I-1",
        "answer_mismatch",
        IssueSeverity.HIGH,
        0.95,
        True,
        "minimal correction",
        ("Demo",),
        (
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
        "x=10",
        "x=12",
        ({"reason": "The final answer must satisfy the problem."},),
        ("layout",),
    )


def plan() -> RepairPlan:
    scene = extract_scenes(BEFORE)[0]
    return RepairPlan(
        "plan-1",
        code_hash(BEFORE),
        (issue(),),
        ("Demo",),
        (EditRegion("Demo", scene.line_start, scene.line_end),),
        ("layout",),
    )


def validation(repair_plan: RepairPlan):
    diff = evaluate_logic_diff(BEFORE, AFTER, repair_plan)
    return diff, validate_candidate(BEFORE, AFTER, repair_plan, diff)
