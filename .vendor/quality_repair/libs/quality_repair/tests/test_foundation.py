from pathlib import Path

from libs.quality_repair import Budget, CheckResult, RepairBundle, ToolBox, budget_for, repair
from libs.quality_repair.statuses import ALL_STATUSES, REPAIR_UNCHANGED
from libs.quality_repair.testing import StubChecker


def test_six_statuses_match_repair_lab_values():
    assert set(ALL_STATUSES) == {
        "SUCCESS_CLEAN", "SUCCESS_DEGRADED", "REPAIR_FAILED",
        "REPAIR_WORSE", "REPAIR_UNCHANGED", "REVIEW_ERROR",
    }


def test_budget_tiers():
    assert budget_for("logic", 1).token_hard_cap == 40_000
    assert budget_for("layout", 2).token_hard_cap == 60_000
    assert budget_for("layout", 8).max_rounds == 2
    assert budget_for("layout", 20).token_hard_cap == 60_000
    assert budget_for("layout", 20).no_progress_stop == 1


def test_check_result_signature_stable():
    a = CheckResult(ok=True, passed=False, blocking_count=1,
                    issues=[{"kind": "overlap", "a": "t1", "b": "t2"}])
    b = CheckResult(ok=True, passed=False, blocking_count=1,
                    issues=[{"kind": "overlap", "a": "t1", "b": "t2"}])
    assert a.signature == b.signature


def test_repair_placeholder_fail_open(tmp_path: Path):
    code = tmp_path / "candidate.py"
    code.write_text("print('hi')\n", encoding="utf-8")
    bundle = RepairBundle(job_id="j1", code_path=code)
    toolbox = ToolBox(checker=StubChecker([CheckResult(ok=True, passed=True, blocking_count=0)]))
    result = repair(bundle, toolbox)
    assert result.status == REPAIR_UNCHANGED
    assert result.code_path == code
