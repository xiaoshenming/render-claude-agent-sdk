"""String literal preservation tests for quality_repair acceptance."""

from pathlib import Path

from libs.quality_repair.acceptance import judge
from libs.quality_repair.schemas import CheckResult
from libs.quality_repair.statuses import REPAIR_WORSE, SUCCESS_DEGRADED
from libs.quality_repair.testing import StubChecker


def test_protect_string_literals_pass_when_preserved(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(ok=True, passed=False, blocking_count=1)
    checker = StubChecker([after])
    input_code = "t = Tex('勾股定理')\n"
    output_code = "t = Tex('勾股定理')\nu = Tex('推论')\n"
    protected = {"protect_string_literals": True}

    report = judge(
        workdir=tmp_path,
        input_code=input_code,
        output_code=output_code,
        before=before,
        checker=checker,
        protected=protected,
    )

    assert report.gates["diff_audit"] == "pass"
    assert report.status == SUCCESS_DEGRADED


def test_protect_string_literals_fail_when_removed(tmp_path: Path):
    before = CheckResult(ok=True, passed=False, blocking_count=2)
    after = CheckResult(ok=True, passed=False, blocking_count=1)
    checker = StubChecker([after])
    input_code = "t = Tex('勾股定理')\n"
    output_code = "t = Tex('毕氏定理')\n"
    protected = {"protect_string_literals": True}

    report = judge(
        workdir=tmp_path,
        input_code=input_code,
        output_code=output_code,
        before=before,
        checker=checker,
        protected=protected,
    )

    assert report.gates["diff_audit"] == "fail"
    assert report.status == REPAIR_WORSE
