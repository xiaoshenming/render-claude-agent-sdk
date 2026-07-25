from pathlib import Path

import pytest

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.profile import coder_profile
from manim_quality.agents.runtime import (
    AgentRuntime,
    BackendRequest,
    BackendResult,
    RuntimeControls,
)
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink
from manim_quality.logic._scene_evidence import extract_scenes
from manim_quality.logic.coder import LogicCoder, LogicCoderError
from manim_quality.logic.repair_plan import EditRegion, RepairPlan
from manim_quality.logic.schemas import (
    CitationArtifact,
    EvidenceCitation,
    IssueSeverity,
    LogicIssue,
)
from manim_quality.revisions.fingerprint import code_hash, sha256_text

CODE = """from manim import *

HELPER = 12

class Demo(Scene):
    def construct(self):
        answer = MathTex("x=12")
        self.add(answer)
"""


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class EditBackend:
    def __init__(self, old: str, new: str) -> None:
        self.old = old
        self.new = new
        self.request: BackendRequest | None = None

    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        self.request = request
        controls.record_round_usage(TokenUsage(input_tokens=30, output_tokens=10))
        path = Path(request.editable_paths[0])
        controls.authorize_tool("Read", {"file_path": str(path)})
        controls.authorize_tool(
            "Edit",
            {"file_path": str(path), "old_string": self.old, "new_string": self.new},
        )
        path.write_text(
            path.read_text(encoding="utf-8").replace(self.old, self.new),
            encoding="utf-8",
        )
        output = {"status": "patched", "summary": "minimal edit", "risk_flags": []}
        controls.authorize_output_submission(output)
        return controls.complete(output)


def limits() -> BudgetLimits:
    return BudgetLimits(100_000, 2, 4, 10_000, 2_000, 1_000, 1_000, 1_000, 4_000)


def plan() -> RepairPlan:
    scene = extract_scenes(CODE)[0]
    issue = LogicIssue(
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
                code_hash(CODE),
                'answer = MathTex("x=12")',
                "Demo",
                7,
                7,
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
        acceptance_predicates=(
            {"kind": "text_absent", "value": "x=12", "scene_id": "Demo"},
            {"kind": "text_present", "value": "x=10", "scene_id": "Demo"},
        ),
        non_goals=("layout",),
    )
    return RepairPlan(
        "plan-1",
        code_hash(CODE),
        (issue,),
        ("Demo",),
        (EditRegion("Demo", scene.line_start, scene.line_end),),
        ("layout",),
    )


def coder(backend: EditBackend) -> LogicCoder:
    runtime = AgentRuntime(backend, MemorySink(), limits())
    profile = coder_profile(model="fake", prompt_version="logic-coder-v1")
    return LogicCoder(runtime, profile)


def run(coder_service: LogicCoder, tmp_path: Path):
    candidate = tmp_path / "candidate.py"
    candidate.write_text(CODE, encoding="utf-8")
    return coder_service.patch(
        run_id="repair-1",
        plan=plan(),
        workspace=tmp_path,
        candidate_path=candidate,
        estimated_input_tokens=200,
        reserved_output_tokens=100,
    )


def test_coder_uses_read_edit_and_returns_externally_validated_patch(
    tmp_path: Path,
) -> None:
    backend = EditBackend("x=12", "x=10")

    result = run(coder(backend), tmp_path)

    assert "x=10" in result.candidate_code
    assert result.diff.passed is True
    assert result.validation.passed is True
    assert backend.request is not None
    assert backend.request.allowed_tools == ("Edit", "Read")
    assert CODE not in backend.request.prompt
    assert "Read `candidate.py` exactly once" in backend.request.prompt


def test_coder_rolls_back_out_of_scope_edit(tmp_path: Path) -> None:
    backend = EditBackend("HELPER = 12", "HELPER = 10")
    candidate = tmp_path / "candidate.py"
    candidate.write_text(CODE, encoding="utf-8")

    with pytest.raises(LogicCoderError, match="outside declared Scenes"):
        coder(backend).patch(
            run_id="repair-1",
            plan=plan(),
            workspace=tmp_path,
            candidate_path=candidate,
            estimated_input_tokens=200,
            reserved_output_tokens=100,
        )

    assert candidate.read_text(encoding="utf-8") == CODE


def test_coder_rejects_noop_and_restores_candidate(tmp_path: Path) -> None:
    backend = EditBackend("missing", "replacement")

    with pytest.raises(LogicCoderError, match="no changes"):
        run(coder(backend), tmp_path)

    assert (tmp_path / "candidate.py").read_text(encoding="utf-8") == CODE
