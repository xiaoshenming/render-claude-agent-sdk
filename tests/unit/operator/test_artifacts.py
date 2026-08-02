import json
from pathlib import Path

import pytest

from manim_quality.agents.usage import AgentCallRecord, TokenUsage, ToolCallRecord
from manim_quality.operator.agent import QualityOperatorResult
from manim_quality.operator.artifacts import write_run_artifacts
from manim_quality.operator.gate import GateDecision, GateResult
from manim_quality.operator.models import ValidationOutcome
from manim_quality.operator.session import QualitySession

PROBLEM = "Construct a line."
CODE = (
    f'"""{PROBLEM}"""\n'
    "class Solution(BaseConfigScene):\n"
    "    def construct(self):\n"
    "        pass\n"
)


def agent_record() -> AgentCallRecord:
    return AgentCallRecord(
        run_id="run-1",
        role="operator",
        model="model",
        prompt="bounded prompt",
        prompt_version="quality-operator-v1",
        schema_version="agent-output-v1",
        tool_version="managed-tools-v1",
        structured_output={"status": "submitted"},
        tool_calls=(
            ToolCallRecord(
                name="mcp__quality__submit_revision",
                input={"revision_id": "R0"},
                allowed=True,
                result_status="ok",
                result_hash="sha256:" + "1" * 64,
                call_id="tool-1",
                started_at_ms=100,
                finished_at_ms=160,
                duration_ms=60,
            ),
        ),
        usage=TokenUsage(input_tokens=100, output_tokens=20),
        turns=4,
        observed_model_rounds=4,
        elapsed_ms=500,
        error=None,
    )


def accepted_fixture():
    session = QualitySession(problem_text=PROBLEM, candidate_code=CODE)
    session.mark_solution_read("R0")
    session.record_findings(())
    session.record_layout_inspection(
        revision_id="R0",
        fingerprint="sha256:" + "2" * 64,
    )
    revision = session.submit("R0")
    operator = QualityOperatorResult(
        revision=revision,
        summary="clean",
        call_record=agent_record(),
        sdk_messages=({
            "kind": "assistant",
            "parent_tool_use_id": "reviewer-call-1",
            "usage": {"input_tokens": 10, "output_tokens": 2},
            "content": [],
        }, {
            "kind": "user",
            "parent_tool_use_id": None,
            "content": [{
                "tool_use_id": "submit-1",
                "is_error": False,
                "content": "accepted",
            }],
        }),
    )
    gate = GateResult(
        decision=GateDecision.PROPOSED,
        final_revision=revision,
        rollback_revision=None,
        reasons=(),
        validation=ValidationOutcome(
            passed=True,
            improved=True,
            summary="independent validation passed",
            details={"rendered": True},
            revision_id=revision.revision_id,
            code_hash=revision.code_hash,
            problem_hash=session.problem_hash,
        ),
        layout_report={
            "revision_id": revision.revision_id,
            "code_hash": revision.code_hash,
            "problem_hash": session.problem_hash,
            "blocking_count": 0,
            "verified": True,
        },
    )
    return session, operator, gate


def test_artifact_writer_persists_replayable_run_pack(tmp_path: Path) -> None:
    session, operator, gate = accepted_fixture()

    write_run_artifacts(
        root=tmp_path,
        session=session,
        operator_result=operator,
        gate_result=gate,
    )

    assert (tmp_path / "input" / "problem.snapshot").read_text(
        encoding="utf-8"
    ) == PROBLEM
    assert (tmp_path / "input" / "candidate.R0.py").read_text(
        encoding="utf-8"
    ) == CODE
    assert (tmp_path / "revisions" / "R0.baseline.py").is_file()
    assert (tmp_path / "logs" / "agent_call.json").is_file()
    assert (tmp_path / "logs" / "tool_calls.jsonl").is_file()
    tool_call = json.loads(
        (tmp_path / "logs" / "tool_calls.jsonl").read_text(encoding="utf-8")
    )
    assert tool_call["call_id"] == "tool-1"
    assert tool_call["duration_ms"] == 60
    assert "reviewer-call-1" in (
        tmp_path / "logs" / "reviewer-sdk-messages.jsonl"
    ).read_text(encoding="utf-8")
    assert "accepted" in (
        tmp_path / "logs" / "tool-results.jsonl"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "evidence" / "revisions.json").is_file()
    assert (tmp_path / "evidence" / "validation.R0.json").is_file()
    assert (tmp_path / "evidence" / "layout.R0.json").is_file()
    assert (tmp_path / "output" / "proposed_candidate.py").read_text(
        encoding="utf-8"
    ) == CODE
    decision = json.loads(
        (tmp_path / "output" / "decision.json").read_text(encoding="utf-8")
    )
    assert decision["decision"] == "PROPOSED"
    assert decision["tokens"]["total_tokens"] == 120


def test_artifact_writer_preserves_owned_runtime_directories(
    tmp_path: Path,
) -> None:
    session, operator, gate = accepted_fixture()
    runtime_file = tmp_path / "agent_runtime" / "R0" / "render.log"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("rendered", encoding="utf-8")

    write_run_artifacts(
        root=tmp_path,
        session=session,
        operator_result=operator,
        gate_result=gate,
    )

    assert runtime_file.read_text(encoding="utf-8") == "rendered"


def test_artifact_writer_rejects_unknown_existing_content(tmp_path: Path) -> None:
    session, operator, gate = accepted_fixture()
    (tmp_path / "unowned.txt").write_text("do not overwrite", encoding="utf-8")

    with pytest.raises(ValueError, match="unknown existing"):
        write_run_artifacts(
            root=tmp_path,
            session=session,
            operator_result=operator,
            gate_result=gate,
        )


def test_artifact_writer_outputs_rollback_not_delivery_on_hold(
    tmp_path: Path,
) -> None:
    session, operator, _gate = accepted_fixture()
    hold = GateResult(
        decision=GateDecision.HOLD,
        final_revision=None,
        rollback_revision=session.baseline,
        reasons=("full_render_not_verified",),
        validation=None,
        layout_report={"blocking_count": 0},
    )

    write_run_artifacts(
        root=tmp_path,
        session=session,
        operator_result=operator,
        gate_result=hold,
    )

    assert not (tmp_path / "output" / "candidate.py").exists()
    assert (tmp_path / "output" / "rollback.R0.py").read_text(
        encoding="utf-8"
    ) == CODE
