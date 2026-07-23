from pathlib import Path
from types import SimpleNamespace

from manim_quality.logic._scene_evidence import extract_scenes
from manim_quality.logic.coder import LogicCoderError
from manim_quality.logic.diff_guard import evaluate_logic_diff
from manim_quality.logic.repair_flow import LogicRepairFlow, RepairFlowStatus
from manim_quality.logic.repair_plan import EditRegion, RepairPlan
from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicIssue,
)
from manim_quality.logic.validators.registry import validate_candidate
from manim_quality.revisions.fingerprint import code_hash, sha256_text

BASELINE = """from manim import *

class SceneOne(Scene):
    def construct(self):
        self.add(MathTex("x=12"))

class SceneTwo(Scene):
    def construct(self):
        self.add(Text("AB parallel CD"))
"""
FIRST_PATCH = BASELINE.replace("x=12", "x=10")
SECOND_PATCH = FIRST_PATCH.replace("AB parallel CD", "AB perpendicular CD")


def issue(
    issue_id: str,
    scene_id: str,
    observed: str,
    expected: str,
    predicates=({"reason": "Frozen semantic claim requires directed verification."},),
) -> LogicIssue:
    line = next(
        i for i, value in enumerate(BASELINE.splitlines(), 1) if observed in value
    )
    return LogicIssue(
        issue_id,
        "logic_mismatch",
        IssueSeverity.HIGH,
        0.95,
        True,
        "minimal scene-local correction",
        (scene_id,),
        (
            EvidenceCitation(
                CitationArtifact.CANDIDATE_CODE,
                "candidate.py",
                code_hash(BASELINE),
                BASELINE.splitlines()[line - 1].strip(),
                scene_id,
                line,
                line,
            ),
            EvidenceCitation(
                CitationArtifact.PROBLEM_TEXT,
                "problem.txt",
                sha256_text(expected),
                expected,
            ),
        ),
        expected,
        observed,
        predicates,
        ("layout",),
    )


def plan() -> RepairPlan:
    scenes = extract_scenes(BASELINE)
    issues = (
        issue("I-1", "SceneOne", "x=12", "x=10"),
        issue("I-2", "SceneTwo", "AB parallel CD", "AB perpendicular CD"),
    )
    return RepairPlan(
        "plan-1",
        code_hash(BASELINE),
        issues,
        tuple(scene.scene_id for scene in scenes),
        tuple(
            EditRegion(scene.scene_id, scene.line_start, scene.line_end)
            for scene in scenes
        ),
        ("layout",),
        2,
    )


def measurable_plan() -> RepairPlan:
    scenes = extract_scenes(BASELINE)
    issues = (
        issue(
            "I-1",
            "SceneOne",
            "x=12",
            "x=10",
            ({"kind": "text_present", "value": "x=10", "scene_id": "SceneOne"},),
        ),
        issue("I-2", "SceneTwo", "AB parallel CD", "AB perpendicular CD"),
    )
    return RepairPlan(
        "plan-measurable",
        code_hash(BASELINE),
        issues,
        tuple(scene.scene_id for scene in scenes),
        tuple(
            EditRegion(scene.scene_id, scene.line_start, scene.line_end)
            for scene in scenes
        ),
        ("layout",),
        2,
    )


class FakeCoder:
    def __init__(self, candidates: list[str]) -> None:
        self.candidates = candidates
        self.calls: list[dict[str, object]] = []

    def patch(self, **kwargs):
        self.calls.append(kwargs)
        before = Path(kwargs["candidate_path"]).read_text(encoding="utf-8")
        after = self.candidates[len(self.calls) - 1]
        Path(kwargs["candidate_path"]).write_text(after, encoding="utf-8")
        diff = evaluate_logic_diff(before, after, kwargs["plan"])
        validation = validate_candidate(before, after, kwargs["plan"], diff)
        return SimpleNamespace(candidate_code=after, diff=diff, validation=validation)


class FakeVerifier:
    def __init__(self, results: list[SimpleNamespace]) -> None:
        self.results = results
        self.calls: list[dict[str, object]] = []

    def verify(self, **kwargs):
        self.calls.append(kwargs)
        return self.results[len(self.calls) - 1]


def verifier_result(verified: bool, resolved: tuple[str, ...]):
    return SimpleNamespace(
        verified=verified,
        decision="verified" if verified else "rejected",
        resolved_issue_ids=resolved,
        review_gaps=(),
    )


def run(
    tmp_path: Path,
    coder: FakeCoder,
    verifier: FakeVerifier,
    repair_plan: RepairPlan | None = None,
):
    candidate = tmp_path / "candidate.py"
    candidate.write_text(BASELINE, encoding="utf-8")
    return LogicRepairFlow(coder, verifier).run(
        run_id="flow-1",
        plan=repair_plan or plan(),
        workspace=tmp_path,
        candidate_path=candidate,
        coder_estimated_input_tokens=100,
        coder_reserved_output_tokens=100,
        verifier_estimated_input_tokens=100,
        verifier_reserved_output_tokens=100,
    )


def test_flow_allows_second_attempt_only_after_deterministic_resolution(
    tmp_path: Path,
) -> None:
    coder = FakeCoder([FIRST_PATCH, SECOND_PATCH])
    verifier = FakeVerifier(
        [verifier_result(False, ()), verifier_result(True, ("I-2",))]
    )

    result = run(tmp_path, coder, verifier, measurable_plan())

    assert result.status is RepairFlowStatus.CANDIDATE_READY
    assert result.attempt_count == 2
    assert result.requires_render is True
    assert coder.calls[1]["retry_context"]["resolved_issue_ids"] == ["I-1"]


def test_flow_keeps_candidate_as_risk_when_verifier_cannot_measure_improvement(
    tmp_path: Path,
) -> None:
    coder = FakeCoder([FIRST_PATCH, SECOND_PATCH])
    verifier = FakeVerifier([verifier_result(False, ())])

    result = run(tmp_path, coder, verifier)

    assert result.status is RepairFlowStatus.CANDIDATE_RISK
    assert result.attempt_count == 2
    assert len(coder.calls) == 2
    assert result.requires_render is True
    assert result.candidate_code == FIRST_PATCH
    assert "best candidate preserved" in result.reason
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == FIRST_PATCH


def test_flow_keeps_unverified_agent_patch_as_risk(tmp_path: Path) -> None:
    coder = FakeCoder([FIRST_PATCH, SECOND_PATCH])
    verifier = FakeVerifier([verifier_result(False, ("I-1",))])

    result = run(tmp_path, coder, verifier)

    assert result.status is RepairFlowStatus.CANDIDATE_RISK
    assert result.attempt_count == 2
    assert len(coder.calls) == 2
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == FIRST_PATCH


def test_flow_uses_deterministic_progress_to_allow_second_attempt(
    tmp_path: Path,
) -> None:
    coder = FakeCoder([FIRST_PATCH, SECOND_PATCH])
    verifier = FakeVerifier(
        [verifier_result(False, ()), verifier_result(True, ("I-2",))]
    )

    result = run(tmp_path, coder, verifier, measurable_plan())

    assert result.status is RepairFlowStatus.CANDIDATE_READY
    assert result.attempt_count == 2
    assert coder.calls[1]["retry_context"]["resolved_issue_ids"] == ["I-1"]


def test_flow_preserves_best_candidate_when_verifier_raises_unexpected_error(
    tmp_path: Path,
) -> None:
    class ExplodingVerifier:
        def verify(self, **kwargs):
            raise RuntimeError("unexpected verifier failure")

    coder = FakeCoder([FIRST_PATCH, FIRST_PATCH])
    candidate = tmp_path / "candidate.py"
    candidate.write_text(BASELINE, encoding="utf-8")

    result = LogicRepairFlow(coder, ExplodingVerifier()).run(
        run_id="flow-error",
        plan=plan(),
        workspace=tmp_path,
        candidate_path=candidate,
        coder_estimated_input_tokens=100,
        coder_reserved_output_tokens=100,
        verifier_estimated_input_tokens=100,
        verifier_reserved_output_tokens=100,
    )

    assert result.status is RepairFlowStatus.CANDIDATE_RISK
    assert "unexpected verifier failure" in result.reason
    assert candidate.read_text(encoding="utf-8") == FIRST_PATCH


def test_flow_counts_a_coder_rejection_as_an_attempt(tmp_path: Path) -> None:
    class RejectingCoder:
        def patch(self, **kwargs):
            raise LogicCoderError("no valid patch")

    result = run(tmp_path, RejectingCoder(), FakeVerifier([]))

    assert result.status is RepairFlowStatus.REJECTED
    assert result.attempt_count == 2


def test_flow_retries_transient_coder_error_before_any_edit(tmp_path: Path) -> None:
    delegate = FakeCoder([FIRST_PATCH])

    class TransientCoder:
        calls = 0

        def patch(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise LogicCoderError("assistant error: server_error")
            return delegate.patch(**kwargs)

    result = run(
        tmp_path,
        TransientCoder(),
        FakeVerifier([verifier_result(True, ("I-1", "I-2"))]),
    )

    assert result.status is RepairFlowStatus.CANDIDATE_READY
    assert result.attempt_count == 2


def test_flow_preserves_edit_when_coder_reports_budget_error(tmp_path: Path) -> None:
    class EditedThenRejectedCoder:
        def patch(self, **kwargs):
            Path(kwargs["candidate_path"]).write_text(FIRST_PATCH, encoding="utf-8")
            raise LogicCoderError("BudgetExceeded: output tokens exceed hard limit")

    result = run(tmp_path, EditedThenRejectedCoder(), FakeVerifier([]))

    assert result.status is RepairFlowStatus.CANDIDATE_RISK
    assert result.attempt_count == 2
    assert result.candidate_code == FIRST_PATCH
    assert "BudgetExceeded" in result.reason
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == FIRST_PATCH


def test_flow_preserves_duplicate_best_patch_as_risk_and_never_starts_third(
    tmp_path: Path,
) -> None:
    coder = FakeCoder([FIRST_PATCH, FIRST_PATCH, SECOND_PATCH])
    verifier = FakeVerifier([verifier_result(False, ()), verifier_result(False, ())])

    result = run(tmp_path, coder, verifier, measurable_plan())

    assert result.status is RepairFlowStatus.CANDIDATE_RISK
    assert result.attempt_count == 2
    assert len(coder.calls) == 2
    assert "duplicate patch" in result.reason
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == FIRST_PATCH


def test_flow_returns_historical_best_when_later_attempt_is_worse(
    tmp_path: Path,
) -> None:
    coder = FakeCoder([FIRST_PATCH, SECOND_PATCH])
    verifier = FakeVerifier(
        [verifier_result(False, ("I-1",)), verifier_result(False, ())]
    )

    result = run(tmp_path, coder, verifier)

    assert result.status is RepairFlowStatus.CANDIDATE_RISK
    assert result.candidate_code == FIRST_PATCH
    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == FIRST_PATCH
