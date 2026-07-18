from pathlib import Path
from typing import ClassVar

from libs.quality_repair.agent.controller import LoopResult, run_repair_loop
from libs.quality_repair.core_candidate_view import build_core_candidate_view
from libs.quality_repair.schemas import AgentRunReport, Budget, CheckResult
from libs.quality_repair.testing import FakeRunner, StubChecker

INPUT_CODE = "# input\nx = 1\n"


def _workdir(tmp_path: Path, code: str = INPUT_CODE) -> Path:
    (tmp_path / "candidate.py").write_text(code, encoding="utf-8")
    return tmp_path


def _check(blocking: int, issues: list[dict] | None = None) -> CheckResult:
    return CheckResult(ok=True, passed=blocking == 0, blocking_count=blocking, issues=issues or [{"kind": "overlap", "a": f"n{blocking}", "b": "z"}])


def _run(workdir: Path, runner, checker, budget: Budget, initial_check: CheckResult):
    return run_repair_loop(
        workdir=workdir,
        prompt="p",
        runner=runner,
        checker=checker,
        budget=budget,
        initial_check=initial_check,
    )


class SequenceRunner:
    name: ClassVar[str] = "sequence"

    def __init__(self, codes: list[str]) -> None:
        self._codes = list(codes)
        self.runs = 0

    def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
        code = self._codes[min(self.runs, len(self._codes) - 1)]
        self.runs += 1
        (workdir / "candidate.py").write_text(code, encoding="utf-8")
        return AgentRunReport(changed=True, tokens_used=100)


def test_zero_blocking_stops_early(tmp_path: Path):
    wd = _workdir(tmp_path)
    result = _run(wd, FakeRunner(new_code="# fixed\nx = 2\n"), StubChecker([_check(0)]), Budget(max_rounds=3), _check(2))

    assert isinstance(result, LoopResult)
    assert result.stop_reason == "zero_blocking"
    assert result.changed is True
    assert result.best_check.blocking_count == 0
    assert (wd / "candidate.py").read_text() == "# fixed\nx = 2\n"
    assert result.rounds_used == 1


def test_worsen_rolls_back_to_input(tmp_path: Path):
    wd = _workdir(tmp_path)
    result = _run(wd, FakeRunner(new_code="# worse\nx = 3\n"), StubChecker([_check(5)]), Budget(max_rounds=1), _check(2))

    assert result.stop_reason == "round_cap"
    assert result.changed is False
    assert (wd / "candidate.py").read_text() == INPUT_CODE
    assert result.best_check.blocking_count == 2


def test_rejected_round_records_attempted_code_and_check_detail(tmp_path: Path):
    wd = _workdir(tmp_path)
    issues = [{"kind": "overlap", "a": "A", "b": "B"}]
    result = _run(
        wd,
        FakeRunner(new_code="# rejected\nx = 99\n"),
        StubChecker([_check(5, issues)]),
        Budget(max_rounds=1),
        _check(2),
    )

    row = result.rounds[0]
    assert row["attempted_changed"] is True
    assert row["accepted"] is False
    assert row["before_blocking"] == 2
    assert row["after_blocking"] == 5
    assert row["attempted_code"] == "# rejected\nx = 99\n"
    assert row["check_after"]["blocking_count"] == 5
    assert row["check_after"]["passed"] is False
    assert row["check_after"]["issues"] == issues
    assert row["check_after"]["error"] is None


def test_no_progress_stops(tmp_path: Path):
    wd = _workdir(tmp_path)
    result = _run(
        wd,
        FakeRunner(new_code="# same\nx = 9\n"),
        StubChecker([_check(3), _check(3)]),
        Budget(max_rounds=5, no_progress_stop=2, same_signature_stop=9),
        _check(3),
    )
    assert result.stop_reason == "no_progress"
    assert result.rounds_used == 2


def test_same_signature_stops(tmp_path: Path):
    wd = _workdir(tmp_path)
    same = [{"kind": "overlap", "a": "t1", "b": "t2"}]
    result = _run(wd, SequenceRunner(["# s1\nx = 4\n", "# s2\nx = 4\n"]), StubChecker([_check(2, same), _check(2, same)]), Budget(max_rounds=5, no_progress_stop=9, same_signature_stop=2), _check(3))
    assert result.stop_reason == "same_signature"


def test_token_hard_cap_stops(tmp_path: Path):
    wd = _workdir(tmp_path)
    result = _run(wd, FakeRunner(new_code="# t\nx = 5\n", tokens_per_run=1000), StubChecker([_check(3)]), Budget(max_rounds=5, token_hard_cap=500), _check(3))
    assert result.stop_reason == "token_cap"
    assert result.tokens_used == 1000


def test_token_cap_does_not_stop_after_improving_edit(tmp_path: Path):
    class HighTokenSequenceRunner:
        name: ClassVar[str] = "high_token_sequence"

        def __init__(self) -> None:
            self.runs = 0

        def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
            self.runs += 1
            (workdir / "candidate.py").write_text(f"# improved {self.runs}\nx = {self.runs}\n", encoding="utf-8")
            return AgentRunReport(changed=True, tokens_used=1000)

    wd = _workdir(tmp_path)
    result = _run(
        wd,
        HighTokenSequenceRunner(),
        StubChecker([_check(2), _check(1)]),
        Budget(max_rounds=2, token_hard_cap=500, no_progress_stop=9, same_signature_stop=9),
        _check(3),
    )

    assert result.stop_reason == "round_cap"
    assert result.tokens_used == 2000
    assert result.best_check.blocking_count == 1


def test_low_residual_improvement_stops_before_second_round_when_budget_allows(tmp_path: Path):
    wd = _workdir(tmp_path)
    result = _run(
        wd,
        SequenceRunner(["# improved\nx = 2\n", "# overreach\nx = 99\n"]),
        StubChecker([_check(2), _check(0)]),
        Budget(
            max_rounds=2,
            no_progress_stop=9,
            same_signature_stop=9,
            accept_degraded_max_blocking=2,
            accept_degraded_min_reduction_ratio=0.5,
        ),
        _check(8),
    )

    assert result.stop_reason == "accepted_degraded_low_residual"
    assert result.rounds_used == 1
    assert result.changed is True
    assert result.best_check.blocking_count == 2
    assert (wd / "candidate.py").read_text(encoding="utf-8") == "# improved\nx = 2\n"


def test_high_residual_improvement_can_continue_to_second_round(tmp_path: Path):
    wd = _workdir(tmp_path)
    result = _run(
        wd,
        SequenceRunner(["# improved\nx = 2\n", "# clean\nx = 3\n"]),
        StubChecker([_check(12), _check(0)]),
        Budget(
            max_rounds=2,
            no_progress_stop=9,
            same_signature_stop=9,
            accept_degraded_max_blocking=2,
            accept_degraded_min_reduction_ratio=0.5,
        ),
        _check(37),
    )

    assert result.stop_reason == "zero_blocking"
    assert result.rounds_used == 2
    assert result.best_check.blocking_count == 0
    assert (wd / "candidate.py").read_text(encoding="utf-8") == "# clean\nx = 3\n"


def test_risk_only_residual_stops_before_second_round_when_budget_allows(tmp_path: Path):
    wd = _workdir(tmp_path)
    risk_issues = [
        {"category": "label_shape_overlap_risk", "a": "label", "b": "line"},
        {"category": "label_shape_overlap_risk", "a": "label2", "b": "line2"},
        {"category": "label_shape_overlap_risk", "a": "label3", "b": "line3"},
    ]
    result = _run(
        wd,
        SequenceRunner(["# improved\nx = 2\n", "# overreach\nx = 99\n"]),
        StubChecker([_check(3, risk_issues), _check(0)]),
        Budget(
            max_rounds=2,
            no_progress_stop=9,
            same_signature_stop=9,
            accept_degraded_max_blocking=2,
            accept_risk_only_max_blocking=6,
        ),
        _check(8),
    )

    assert result.stop_reason == "accepted_degraded_low_residual"
    assert result.rounds_used == 1
    assert result.best_check.blocking_count == 3


def test_runner_error_stops(tmp_path: Path):
    wd = _workdir(tmp_path)
    checker = StubChecker([_check(0)])
    result = _run(wd, FakeRunner(error="boom"), checker, Budget(max_rounds=3), _check(2))

    assert result.stop_reason == "runner_error_no_edit"
    assert result.changed is False
    assert (wd / "candidate.py").read_text() == INPUT_CODE
    assert result.rounds[0]["error"] == "boom"
    assert result.rounds[0]["error_class"] == "runner_error_no_edit"
    assert checker.calls == 0


def test_runner_error_preserves_reported_token_usage(tmp_path: Path):
    class ErrorWithTokensRunner:
        name: ClassVar[str] = "error_with_tokens"

        def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
            return AgentRunReport(changed=False, tokens_used=1234, error="turn_cap")

    result = _run(_workdir(tmp_path), ErrorWithTokensRunner(), StubChecker([_check(0)]), Budget(max_rounds=3), _check(2))

    assert result.stop_reason == "runner_error_no_edit"
    assert result.tokens_used == 1234
    assert result.rounds[0]["tokens"] == 1234


def test_runner_error_after_file_edit_is_still_checked(tmp_path: Path):
    class ErrorAfterEditRunner:
        name: ClassVar[str] = "error_after_edit"

        def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
            (workdir / "candidate.py").write_text("# fixed despite turn cap\n", encoding="utf-8")
            return AgentRunReport(changed=False, tokens_used=260_000, error="turn_cap")

    wd = _workdir(tmp_path)
    result = _run(wd, ErrorAfterEditRunner(), StubChecker([_check(0)]), Budget(max_rounds=1), _check(8))

    assert result.stop_reason == "zero_blocking"
    assert result.changed is True
    assert result.best_check.blocking_count == 0
    assert (wd / "candidate.py").read_text(encoding="utf-8") == "# fixed despite turn cap\n"


def test_core_candidate_edit_is_composed_before_checker_runs(tmp_path: Path):
    code = "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait()\n"
    wd = _workdir(tmp_path, code)
    build_core_candidate_view(wd)

    class CoreEditRunner:
        name: ClassVar[str] = "core_edit"

        def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
            (workdir / "core_candidate.py").write_text(
                "class Solution(Scene):\n    def construct(self):\n        self.wait(2)\n",
                encoding="utf-8",
            )
            return AgentRunReport(changed=True, tokens_used=100)

    class InspectingChecker:
        calls = 0
        seen_code: list[str]

        def __init__(self) -> None:
            self.seen_code = []

        def run_check(self, code_path: Path, workdir: Path) -> CheckResult:
            self.calls += 1
            self.seen_code.append(code_path.read_text(encoding="utf-8"))
            return _check(0)

    checker = InspectingChecker()
    result = _run(wd, CoreEditRunner(), checker, Budget(max_rounds=1), _check(3))

    assert result.stop_reason == "zero_blocking"
    assert checker.calls == 1
    assert "self.wait(2)" in checker.seen_code[0]
    assert (wd / "candidate.py").read_text(encoding="utf-8") == (
        "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait(2)\n"
    )


def test_core_candidate_rollback_rebuilds_core_from_best_snapshot(tmp_path: Path):
    code = "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait()\n"
    wd = _workdir(tmp_path, code)
    build_core_candidate_view(wd)

    class CoreSequenceRunner:
        name: ClassVar[str] = "core_sequence"

        def __init__(self) -> None:
            self.runs = 0

        def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
            self.runs += 1
            wait_value = 2 if self.runs == 1 else 99
            (workdir / "core_candidate.py").write_text(
                f"class Solution(Scene):\n    def construct(self):\n        self.wait({wait_value})\n",
                encoding="utf-8",
            )
            return AgentRunReport(changed=True, tokens_used=100, final_text='{"action":"fix"}')

    result = _run(
        wd,
        CoreSequenceRunner(),
        StubChecker([_check(2), _check(5)]),
        Budget(max_rounds=2, no_progress_stop=9, same_signature_stop=9),
        _check(3),
    )

    assert result.stop_reason == "round_cap"
    assert result.best_check.blocking_count == 2
    assert "self.wait(2)" in (wd / "candidate.py").read_text(encoding="utf-8")
    assert "self.wait(2)" in (wd / "core_candidate.py").read_text(encoding="utf-8")
    assert "self.wait(99)" not in (wd / "candidate.py").read_text(encoding="utf-8")
    assert "self.wait(99)" not in (wd / "core_candidate.py").read_text(encoding="utf-8")


def test_core_candidate_rejected_round_rolls_back_before_next_round(tmp_path: Path):
    code = "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait()\n"
    wd = _workdir(tmp_path, code)
    build_core_candidate_view(wd)

    class InspectingCoreRunner:
        name: ClassVar[str] = "inspecting_core"

        def __init__(self) -> None:
            self.runs = 0
            self.core_seen: list[str] = []

        def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
            self.runs += 1
            self.core_seen.append((workdir / "core_candidate.py").read_text(encoding="utf-8"))
            wait_value = 99 if self.runs == 1 else 2
            (workdir / "core_candidate.py").write_text(
                f"class Solution(Scene):\n    def construct(self):\n        self.wait({wait_value})\n",
                encoding="utf-8",
            )
            return AgentRunReport(changed=True, tokens_used=100, final_text='{"action":"fix"}')

    runner = InspectingCoreRunner()
    result = _run(
        wd,
        runner,
        StubChecker([_check(5), _check(0)]),
        Budget(max_rounds=2, no_progress_stop=9, same_signature_stop=9),
        _check(3),
    )

    assert result.stop_reason == "zero_blocking"
    assert "self.wait(99)" not in runner.core_seen[1]
    assert "self.wait(2)" in (wd / "core_candidate.py").read_text(encoding="utf-8")
    assert "self.wait(2)" in (wd / "candidate.py").read_text(encoding="utf-8")


def test_agent_no_fix_stops_without_checker_or_edit(tmp_path: Path):
    wd = _workdir(tmp_path)
    checker = StubChecker([_check(0)])
    result = _run(
        wd,
        FakeRunner(final_text='{"action":"no_fix","severity":"risk_only","confidence":0.8}'),
        checker,
        Budget(max_rounds=3),
        _check(2),
    )

    assert result.stop_reason == "agent_no_fix"
    assert result.changed is False
    assert checker.calls == 0
    assert result.rounds[0]["agent_decision"]["action"] == "no_fix"


def test_agent_need_more_evidence_materializes_scoped_query(tmp_path: Path):
    wd = _workdir(tmp_path)
    (wd / "facts").mkdir()
    (wd / "facts" / "layout_context.full.json").write_text(
        '{"top_blocking_issues":[{"category":"text_formula_overlap","a":{"path":"mobjects.1","bbox":{"center_x":1,"center_y":2}},"b":{"path":"mobjects.2","bbox":{"center_x":1,"center_y":2}}}]}',
        encoding="utf-8",
    )
    result = _run(
        wd,
        FakeRunner(
            final_text=(
                '{"action":"need_more_evidence","confidence":0.6,'
                '"evidence_requests":[{"type":"full_bbox_by_issue_id","issue_id":"I001","reason":"verify"}]}'
            )
        ),
        StubChecker([_check(0)]),
        Budget(max_rounds=1),
        _check(2),
    )

    assert result.stop_reason == "round_cap"
    assert result.changed is False
    assert (wd / "evidence_queries" / "round_01" / "results.json").exists()
    assert result.rounds[0]["evidence_query"]["results"][0]["ok"] is True
    assert "issue" not in result.rounds[0]["evidence_query"]["results"][0]


def test_agent_fix_without_edit_is_structured_runner_error(tmp_path: Path):
    wd = _workdir(tmp_path)
    checker = StubChecker([_check(0)])
    result = _run(
        wd,
        FakeRunner(final_text='{"action":"fix","severity":"must_fix","confidence":0.9}'),
        checker,
        Budget(max_rounds=3),
        _check(2),
    )

    assert result.stop_reason == "runner_error_fix_without_edit"
    assert result.changed is False
    assert checker.calls == 0
    assert result.rounds[0]["error_class"] == "runner_error_fix_without_edit"


def test_missing_candidate_fails_open(tmp_path: Path):
    runner = FakeRunner(new_code="# should not run\n")
    checker = StubChecker([_check(0)])
    result = _run(tmp_path, runner, checker, Budget(max_rounds=3), _check(2))

    assert result.stop_reason == "check_error"
    assert result.best_check.error.startswith("candidate_unreadable:")
    assert runner.runs == 0
    assert checker.calls == 0


def test_check_error_rolls_back_best(tmp_path: Path):
    wd = _workdir(tmp_path)
    result = _run(wd, FakeRunner(new_code="# c\nx = 6\n"), StubChecker([CheckResult.failure("checker crashed")]), Budget(max_rounds=3), _check(2))
    assert result.stop_reason == "check_error_after_edit"
    assert (wd / "candidate.py").read_text() == INPUT_CODE


def test_max_rounds_stops(tmp_path: Path):
    wd = _workdir(tmp_path)
    checker = StubChecker([_check(2, [{"kind": "a", "a": "1", "b": "2"}]), _check(1, [{"kind": "b", "a": "3", "b": "4"}])])
    result = _run(wd, SequenceRunner(["# improved1\nx = 7\n", "# improved2\nx = 7\n"]), checker, Budget(max_rounds=2, no_progress_stop=9, same_signature_stop=9), _check(3))

    assert result.stop_reason == "round_cap"
    assert result.rounds_used == 2
    assert result.changed is True
    assert result.best_check.blocking_count == 1


def test_rounds_trace_records_each_round(tmp_path: Path):
    result = _run(_workdir(tmp_path), FakeRunner(new_code="# fixed\n", tokens_per_run=100), StubChecker([_check(0)]), Budget(max_rounds=3), _check(2))
    row = result.rounds[0]
    assert row["round"] == 1
    assert row["blocking"] == 0
    assert row["tokens"] == 100
    assert "signature" in row
