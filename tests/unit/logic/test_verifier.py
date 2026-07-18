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


def test_directed_verifier_binds_exact_patched_candidate_evidence(
    tmp_path: Path,
) -> None:
    line = next(i for i, value in enumerate(AFTER.splitlines(), 1) if "x=10" in value)
    payload = {
        "decision": "verified",
        "results": [
            {
                "issue_id": "I-1",
                "resolved": True,
                "candidate_evidence": {
                    "scene_id": "Demo",
                    "line_start": line,
                    "line_end": line,
                    "excerpt": 'answer = MathTex("x=10")',
                },
                "reason": "The patched claim now matches the expected answer.",
            }
        ],
        "review_gaps": [],
    }
    backend = VerifierBackend(payload)
    runtime = AgentRuntime(backend, MemorySink(), limits())
    candidate = tmp_path / "candidate.py"
    candidate.write_text(AFTER, encoding="utf-8")
    repair_plan = plan()
    diff, report = validation(repair_plan)

    result = DirectedVerifier(
        runtime, verifier_profile(model="fake", prompt_version="verifier-v1")
    ).verify(
        run_id="verify-1",
        plan=repair_plan,
        diff=diff,
        validation=report,
        before_code=BEFORE,
        workspace=tmp_path,
        candidate_path=candidate,
        estimated_input_tokens=100,
        reserved_output_tokens=100,
    )

    assert result.verified is True
    assert result.resolved_issue_ids == ("I-1",)
    assert backend.request is not None
    assert backend.request.allowed_tools == ("Read",)
    assert AFTER not in backend.request.prompt


def test_directed_verifier_accepts_multiple_bound_results_for_one_issue(
    tmp_path: Path,
) -> None:
    line = next(i for i, value in enumerate(AFTER.splitlines(), 1) if "x=10" in value)
    result = {
        "issue_id": "I-1",
        "resolved": True,
        "candidate_evidence": {
            "scene_id": "Demo",
            "line_start": line,
            "line_end": line,
            "excerpt": 'answer = MathTex("x=10")',
        },
        "reason": "The changed claim now matches the expected answer.",
    }
    runtime = AgentRuntime(
        VerifierBackend(
            {
                "decision": "verified",
                "results": [result, dict(result)],
                "review_gaps": [],
            }
        ),
        MemorySink(),
        limits(),
    )
    candidate = tmp_path / "candidate.py"
    candidate.write_text(AFTER, encoding="utf-8")
    repair_plan = plan()
    diff, report = validation(repair_plan)

    verified = DirectedVerifier(
        runtime, verifier_profile(model="fake", prompt_version="verifier-v1")
    ).verify(
        run_id="verify-multiple-evidence",
        plan=repair_plan,
        diff=diff,
        validation=report,
        before_code=BEFORE,
        workspace=tmp_path,
        candidate_path=candidate,
        estimated_input_tokens=100,
        reserved_output_tokens=100,
    )

    assert verified.verified is True
    assert verified.resolved_issue_ids == ("I-1",)


def test_directed_verifier_rejects_unbound_excerpt(tmp_path: Path) -> None:
    payload = {
        "decision": "verified",
        "results": [
            {
                "issue_id": "I-1",
                "resolved": True,
                "candidate_evidence": {
                    "scene_id": "Demo",
                    "line_start": 5,
                    "line_end": 5,
                    "excerpt": "invented code",
                },
                "reason": "claimed fixed",
            }
        ],
        "review_gaps": [],
    }
    runtime = AgentRuntime(VerifierBackend(payload), MemorySink(), limits())
    candidate = tmp_path / "candidate.py"
    candidate.write_text(AFTER, encoding="utf-8")
    repair_plan = plan()
    diff, report = validation(repair_plan)

    with pytest.raises(DirectedVerifierError, match="not present"):
        DirectedVerifier(
            runtime, verifier_profile(model="fake", prompt_version="verifier-v1")
        ).verify(
            run_id="verify-1",
            plan=repair_plan,
            diff=diff,
            validation=report,
            before_code=BEFORE,
            workspace=tmp_path,
            candidate_path=candidate,
            estimated_input_tokens=100,
            reserved_output_tokens=100,
        )


def test_directed_verifier_rejects_resolved_claim_citing_unchanged_code(
    tmp_path: Path,
) -> None:
    payload = {
        "decision": "verified",
        "results": [
            {
                "issue_id": "I-1",
                "resolved": True,
                "candidate_evidence": {
                    "scene_id": "Demo",
                    "line_start": 6,
                    "line_end": 6,
                    "excerpt": "self.add(answer)",
                },
                "reason": "claimed fixed",
            }
        ],
        "review_gaps": [],
    }
    runtime = AgentRuntime(VerifierBackend(payload), MemorySink(), limits())
    candidate = tmp_path / "candidate.py"
    candidate.write_text(AFTER, encoding="utf-8")
    repair_plan = plan()
    candidate_diff, report = validation(repair_plan)

    with pytest.raises(DirectedVerifierError, match="issue source"):
        DirectedVerifier(
            runtime, verifier_profile(model="fake", prompt_version="verifier-v1")
        ).verify(
            run_id="verify-unchanged",
            plan=repair_plan,
            diff=candidate_diff,
            validation=report,
            before_code=BEFORE,
            workspace=tmp_path,
            candidate_path=candidate,
            estimated_input_tokens=100,
            reserved_output_tokens=100,
        )


def test_verifier_changed_evidence_must_match_issue_source_hunk() -> None:
    unrelated = BEFORE.replace(
        "self.add(answer)", 'self.add(answer, Text("unrelated"))'
    )
    evidence = {
        "scene_id": "Demo",
        "line_start": 6,
        "line_end": 6,
        "excerpt": 'self.add(answer, Text("unrelated"))',
    }

    with pytest.raises(ValueError, match="issue source"):
        bind_candidate_evidence(
            evidence,
            BEFORE,
            unrelated,
            plan(),
            "I-1",
            require_changed=True,
        )


def test_verifier_can_bind_adjacent_evidence_after_faulty_line_is_deleted() -> None:
    after = BEFORE.replace('        answer = MathTex("x=12")\n', "")
    evidence = {
        "scene_id": "Demo",
        "line_start": 5,
        "line_end": 5,
        "excerpt": "self.add(answer)",
    }

    bind_candidate_evidence(
        evidence,
        BEFORE,
        after,
        plan(),
        "I-1",
        require_changed=True,
    )


def test_verifier_prompt_describes_multi_evidence_issue_order() -> None:
    prompt = (
        Path(__file__).parents[3]
        / "src/manim_quality/logic/prompts/verifier.md"
    ).read_text(encoding="utf-8")

    assert "one or more results for each unresolved issue" in prompt
