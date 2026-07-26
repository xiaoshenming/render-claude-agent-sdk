import json

from manim_quality.agents._runtime_models import AgentRunFailed
from manim_quality.agents.usage import AgentCallRecord, TokenUsage
from manim_quality.operator.agent import _recover_submitted_output
from manim_quality.operator.failure_artifacts import write_failed_run_artifacts
from manim_quality.operator.models import Finding, FindingCategory, PatchScope
from manim_quality.operator.session import QualitySession

PROBLEM = "Problem: prove AB is parallel to CD."
BASELINE = f'''from manim import *

class Solution(BaseConfigScene):
    """{PROBLEM}"""

    def construct(self):
        line = Line(LEFT, RIGHT)
        self.add(line)
'''


def record(error: str | None, *, usage_complete: bool = False) -> AgentCallRecord:
    return AgentCallRecord(
        run_id="run-1",
        role="quality_operator",
        model="test-model",
        prompt="prompt",
        prompt_version="v1",
        schema_version="v1",
        tool_version="v1",
        structured_output=None,
        tool_calls=(),
        usage=TokenUsage(),
        turns=3,
        observed_model_rounds=3,
        elapsed_ms=1_000,
        error=error,
        external_tool_ms=250,
        usage_complete=usage_complete,
    )


def repaired_session(*, submit: bool) -> QualitySession:
    session = QualitySession(problem_text=PROBLEM, candidate_code=BASELINE)
    session.mark_solution_read("R0")
    session.record_findings(
        (
            Finding(
                finding_id="logic-1",
                category=FindingCategory.LOGIC,
                severity="blocking",
                summary="The constructed relation contradicts the stated proof.",
                acceptance_criteria="The rendered relation matches the problem.",
            ),
        )
    )
    session.apply_patch(
        scope=PatchScope.LOGIC,
        old_text="Line(LEFT, RIGHT)",
        new_text="Line(LEFT, 2 * RIGHT)",
        finding_ids=("logic-1",),
    )
    session.record_validation(
        revision_id="R1",
        passed=True,
        improved=True,
        fingerprint="sha256:" + "1" * 64,
    )
    session.record_layout_inspection(
        revision_id="R1",
        fingerprint="sha256:" + "2" * 64,
        blocking_count=0,
    )
    if submit:
        session.submit("R1")
    return session


def test_submitted_revision_recovers_from_any_terminal_failure() -> None:
    session = repaired_session(submit=True)
    error = AgentRunFailed(record("TimeoutError: session exceeded budget"))

    recovered = _recover_submitted_output(session, error)

    assert recovered is not None
    assert recovered.revision.revision_id == "R1"
    assert "TimeoutError" in recovered.summary


def test_unsubmitted_session_never_recovers_a_candidate() -> None:
    session = repaired_session(submit=False)
    error = AgentRunFailed(record("SDK result has no structured output object"))

    assert _recover_submitted_output(session, error) is None


def test_failed_run_artifacts_classify_timeout_and_keep_best_candidate(
    tmp_path,
) -> None:
    session = repaired_session(submit=False)
    failure_record = record(
        "TimeoutError: Claude Agent SDK session exceeded the reasoning budget"
    )

    write_failed_run_artifacts(
        root=tmp_path / "run",
        session=session,
        record=failure_record,
        baseline_layout_report={"blocking_count": 3},
        error=TimeoutError("session exceeded"),
    )

    failure = json.loads((tmp_path / "run" / "logs" / "failure.json").read_text())
    assert failure["status"] == "FAILED_TIMEOUT"
    assert failure["best_render_passed"] == {
        "revision_id": "R1",
        "blocking_count": 0,
        "layout_inspected": True,
    }
    assert failure["usage_complete"] is False
    assert failure["external_tool_ms"] == 250
    assert (tmp_path / "run" / "output" / "last_candidate.R1.py").is_file()
    assert (tmp_path / "run" / "output" / "best_render_passed.R1.py").is_file()
