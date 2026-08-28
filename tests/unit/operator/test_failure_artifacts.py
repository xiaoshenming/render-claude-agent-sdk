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
                source_reviewer_ids=("math_geometry_reviewer",),
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
    error = TimeoutError("session exceeded")
    error.sdk_messages = ({
        "kind": "assistant",
        "parent_tool_use_id": "reviewer-call-1",
        "usage": {"input_tokens": 10, "output_tokens": 2},
        "content": [],
    }, {
        "kind": "user",
        "parent_tool_use_id": None,
        "content": [{
            "tool_use_id": "read-1",
            "is_error": False,
            "content": "full tool result",
        }],
    })
    error.subagent_results = ({
        "sdk_metadata": {"subagent_tokens": 321},
    },)

    write_failed_run_artifacts(
        root=tmp_path / "run",
        session=session,
        record=failure_record,
        baseline_layout_report={"blocking_count": 3},
        error=error,
    )

    failure = json.loads((tmp_path / "run" / "logs" / "failure.json").read_text())
    assert failure["status"] == "FAILED_TIMEOUT"
    assert failure["best_render_passed"] == {
        "revision_id": "R1",
        "code_hash": session.current_revision.code_hash,
        "render_passed": True,
        "blocking_count": 0,
        "layout_inspected": True,
        "layout_follow_up_required": False,
    }
    assert failure["usage_complete"] is False
    assert failure["reviewer_tokens"] == 321
    assert failure["total_tokens_with_reviewers"] == 321
    assert failure["token_accounting_status"] == "partial"
    assert failure["known_provider_tokens"] == 0
    assert failure["external_tool_ms"] == 250
    reviewer_messages = (
        tmp_path / "run" / "logs" / "reviewer-sdk-messages.jsonl"
    ).read_text(encoding="utf-8")
    tool_results = (
        tmp_path / "run" / "logs" / "tool-results.jsonl"
    ).read_text(encoding="utf-8")
    assert "reviewer-call-1" in reviewer_messages
    assert "full tool result" in tool_results
    assert (tmp_path / "run" / "output" / "last_candidate.R1.py").is_file()
    assert (tmp_path / "run" / "output" / "best_render_passed.R1.py").is_file()
    findings = json.loads(
        (tmp_path / "run" / "evidence" / "findings.json").read_text()
    )
    revisions = json.loads(
        (tmp_path / "run" / "evidence" / "revisions.json").read_text()
    )
    assert findings["findings"][0]["finding_id"] == "logic-1"
    assert findings["findings"][0]["source_reviewer_ids"] == [
        "math_geometry_reviewer"
    ]
    assert revisions["active_revision_id"] == "R1"


def test_failed_run_classifies_max_turns_and_recovers_reviewer_usage(
    tmp_path,
) -> None:
    session = repaired_session(submit=False)
    failure_record = record(None)
    error = RuntimeError("Reached maximum number of turns (24)")
    error.sdk_messages = ({
        "kind": "assistant",
        "message_id": "review-1",
        "parent_tool_use_id": "agent-review-1",
        "usage": {"input_tokens": 120, "output_tokens": 30},
    },)

    write_failed_run_artifacts(
        root=tmp_path / "run",
        session=session,
        record=failure_record,
        baseline_layout_report={"blocking_count": 2},
        error=error,
    )

    failure = json.loads((tmp_path / "run/logs/failure.json").read_text())
    assert failure["status"] == "FAILED_MAX_TURNS"
    assert failure["reviewer_tokens"] == 150
    assert failure["total_tokens_with_reviewers"] == 150
    assert failure["token_accounting_status"] == "partial"


def test_failed_artifacts_preserve_preexisting_usage_ledger(tmp_path) -> None:
    root = tmp_path / "run"
    ledger = root / "logs" / "usage-events.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"role":"operator"}\n', encoding="utf-8")

    write_failed_run_artifacts(
        root=root,
        session=repaired_session(submit=False),
        record=record("TimeoutError: session exceeded"),
        baseline_layout_report={"blocking_count": 1},
        error=TimeoutError("session exceeded"),
    )

    assert ledger.read_text(encoding="utf-8") == '{"role":"operator"}\n'
    assert (root / "logs" / "failure.json").is_file()
