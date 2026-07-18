"""libs.quality_repair.acceptance.judge — 六态判定单测（Stub 注入，无真实 IO 依赖）。"""

from pathlib import Path

from libs.quality_repair.acceptance import judge
from libs.quality_repair.schemas import CheckResult
from libs.quality_repair.statuses import (
    REPAIR_FAILED,
    REPAIR_UNCHANGED,
    REPAIR_WORSE,
    REVIEW_ERROR,
    SUCCESS_CLEAN,
    SUCCESS_DEGRADED,
)
from libs.quality_repair.testing import StubChecker, StubRenderer


def test_unchanged_short_circuit_skips_all_gates(tmp_path: Path):
    checker = StubChecker([CheckResult(ok=True, passed=True, blocking_count=0)])
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    code = "print(1)\n"

    report = judge(workdir=tmp_path, input_code=code, output_code=code, before=before, checker=checker)

    assert report.status == REPAIR_UNCHANGED
    assert all(value == "skip" for value in report.gates.values())
    assert checker.calls == 0
    assert report.after == report.before


def test_all_gates_pass_and_zeroed_is_success_clean(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=3)
    after = CheckResult(ok=True, passed=True, blocking_count=0)
    checker = StubChecker([after])

    report = judge(
        workdir=tmp_path,
        input_code="x = 1\n",
        output_code="x = 2\n",
        before=before,
        checker=checker,
    )

    assert report.status == SUCCESS_CLEAN
    assert report.gates["compile"] == "pass"
    assert report.gates["recheck"] == "pass"
    assert report.after["blocking_count"] == 0


def test_blocking_reduced_but_not_zero_is_success_degraded(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=3)
    after = CheckResult(ok=True, passed=False, blocking_count=1)
    checker = StubChecker([after])

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
    )

    assert report.status == SUCCESS_DEGRADED
    assert report.before["blocking_count"] == 3
    assert report.after["blocking_count"] == 1


def test_blocking_increase_is_repair_worse(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=1)
    after = CheckResult(ok=True, passed=False, blocking_count=4)
    checker = StubChecker([after])

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
    )

    assert report.status == REPAIR_WORSE


def test_syntax_broken_output_is_repair_worse(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=1)
    # 即使 checker 本身天真地返回通过，编译门禁也必须先拦下
    after = CheckResult(ok=True, passed=True, blocking_count=0)
    checker = StubChecker([after])
    bad_code = "def f(:\n    pass\n"

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code=bad_code,
        before=before,
        checker=checker,
    )

    assert report.status == REPAIR_WORSE
    assert report.gates["compile"] == "fail"


def test_checker_crash_is_review_error(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=1)
    checker = StubChecker([CheckResult.failure("probe_timeout")])

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
    )

    assert report.status == REVIEW_ERROR
    assert report.gates["recheck"] == "error"


def test_forbidden_pattern_removed_is_repair_worse(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    # 单看 blocking 是改善的（2->1），但触碰了禁改区，必须判为变差
    after = CheckResult(ok=True, passed=False, blocking_count=1)
    checker = StubChecker([after])
    input_code = "self.play(Write(title))\nx = 1\n"
    output_code = "x = 1\n"
    protected = {"forbidden_patterns": ["Write(title)"]}

    report = judge(
        workdir=tmp_path,
        input_code=input_code,
        output_code=output_code,
        before=before,
        checker=checker,
        protected=protected,
    )

    assert report.status == REPAIR_WORSE
    assert report.gates["diff_audit"] == "fail"


def test_whitespace_only_spacer_literal_removed_is_not_diff_audit_failure(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(ok=True, passed=False, blocking_count=1)
    checker = StubChecker([after])
    input_code = 'row = make_formula_row("A. 5", "    ", "B. 2")\n'
    output_code = 'row = make_formula_row("A. 5", "B. 2")\n'

    report = judge(
        workdir=tmp_path,
        input_code=input_code,
        output_code=output_code,
        before=before,
        checker=checker,
        protected={"protect_string_literals": True},
    )

    assert report.status == SUCCESS_DEGRADED
    assert report.gates["diff_audit"] == "pass"


def test_bbox_explosion_is_repair_worse(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(
        ok=True,
        passed=False,
        blocking_count=1,
        issues=[{"kind": "overlap", "bbox": {"x": 40}}],
    )
    checker = StubChecker([after])
    safe_area = {"x_min": -7.1, "x_max": 7.1}

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
        safe_area=safe_area,
    )

    assert report.status == REPAIR_WORSE
    assert report.gates["bbox_guard"] == "fail"


def test_bbox_explosion_from_raw_bboxes_is_repair_worse(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(
        ok=True,
        passed=False,
        blocking_count=1,
        raw={"bboxes": [{"x_max": 40}]},
    )
    checker = StubChecker([after])
    safe_area = {"x_min": -7.1, "x_max": 7.1}

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
        safe_area=safe_area,
    )

    assert report.status == REPAIR_WORSE
    assert report.gates["bbox_guard"] == "fail"


def test_changed_but_no_progress_is_repair_failed(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(ok=True, passed=False, blocking_count=2)
    checker = StubChecker([after])

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
    )

    assert report.status == REPAIR_FAILED


def test_render_gate_failure_is_repair_worse(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(ok=True, passed=False, blocking_count=1)
    checker = StubChecker([after])
    renderer = StubRenderer(ok=False)

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
        renderer=renderer,
        scene_names=["Scene_01"],
    )

    assert report.status == REPAIR_WORSE
    assert report.gates["render"] == "fail"


def test_render_gate_skipped_without_scene_names(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(ok=True, passed=True, blocking_count=0)
    checker = StubChecker([after])
    renderer = StubRenderer(ok=True)

    report = judge(
        workdir=tmp_path,
        input_code="a = 1\n",
        output_code="a = 2\n",
        before=before,
        checker=checker,
        renderer=renderer,
        scene_names=[],
    )

    assert report.gates["render"] == "skip"
    assert report.status == SUCCESS_CLEAN
