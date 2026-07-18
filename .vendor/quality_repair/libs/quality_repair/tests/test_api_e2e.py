from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from libs.quality_repair import Budget, CheckResult, RepairBundle, ToolBox, repair
from libs.quality_repair.statuses import REPAIR_UNCHANGED, SUCCESS_CLEAN
from libs.quality_repair.testing import FakeRunner, StubChecker


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_case(tmp_path: Path, *, job_id: str = "job-1", code: str = "x = 1\n") -> RepairBundle:
    code_path = tmp_path / "candidate.py"
    code_path.write_text(code, encoding="utf-8")
    layout_context = _write_json(
        tmp_path / "layout_context.json",
        {
            "active_visible_objects": [
                {
                    "path": "A",
                    "class": "Text",
                    "text": "A",
                    "bbox": {"left": 0, "right": 2, "top": 2, "bottom": 0},
                },
                {
                    "path": "B",
                    "class": "Text",
                    "text": "B",
                    "bbox": {"left": 1, "right": 3, "top": 3, "bottom": 1},
                },
            ],
            "top_blocking_issues": [{"a": "A", "b": "B"}],
            "blocking_layout_issue_count": 1,
            "pass": False,
            "status": "layout_failed",
            "safe_area": {"x_min": -7.1, "x_max": 7.1, "y_min": -4, "y_max": 4},
        },
    )
    return RepairBundle(
        job_id=job_id,
        code_path=code_path,
        layout_context=layout_context,
        evidence_root=tmp_path / "evidence",
    )


def _check(blocking: int, *, a: str = "A", b: str = "B") -> CheckResult:
    return CheckResult(
        ok=True,
        passed=blocking == 0,
        blocking_count=blocking,
        issues=[] if blocking == 0 else [{"kind": "overlap", "a": a, "b": b}],
    )


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _force_sdk_runner(monkeypatch: pytest.MonkeyPatch, runner: FakeRunner) -> None:
    monkeypatch.setattr("libs.quality_repair.api.ClaudeSDKRunner", lambda **_: runner)


def test_repair_success_writes_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 2\n", tokens_per_run=123)
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(2), _check(0), _check(0)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == SUCCESS_CLEAN
    assert result.code_path != bundle.code_path
    assert result.code_path.read_text(encoding="utf-8") == "x = 2\n"
    assert result.repairability == "auto_ready"
    assert result.rounds_used == 1
    assert result.tokens_used == 123
    assert result.before["blocking_count"] == 2
    assert result.after["blocking_count"] == 0
    assert (result.evidence_dir / "bundle_manifest.json").exists()
    assert (result.evidence_dir / "round_01" / "prompt.md").read_text(encoding="utf-8").startswith(
        "You are a Manim layout repair agent."
    )
    assert (result.evidence_dir / "round_01" / "usage.json").exists()
    assert (result.evidence_dir / "round_01" / "check_after" / "check_result.json").exists()
    acceptance = _read_json(result.evidence_dir / "acceptance.json")
    summary = _read_json(result.evidence_dir / "summary.json")
    assert acceptance["status"] == SUCCESS_CLEAN
    assert summary["passed"] is True
    assert summary["changed"] is True
    assert summary["improved"] is True
    assert summary["worsened"] is False


def test_repair_layout_uses_core_candidate_view_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code = (
        "from manim import *\n\n"
        "class Solution(Scene):\n"
        "    def construct(self):\n"
        "        self.wait()\n"
    )
    bundle = _write_case(tmp_path, job_id="core-view", code=code)

    class CoreRunner:
        name = "core_runner"
        runs = 0

        def run(self, workdir: Path, prompt: str, budget: Budget):
            self.runs += 1
            assert f"Read {workdir / 'core_candidate.py'} once" in prompt
            assert str(workdir / "layout_issue_digest.json") in prompt
            assert "Do not read candidate.py" in prompt
            (workdir / "core_candidate.py").write_text(
                "class Solution(Scene):\n    def construct(self):\n        self.wait(2)\n",
                encoding="utf-8",
            )
            from libs.quality_repair.schemas import AgentRunReport

            return AgentRunReport(changed=True, tokens_used=111, final_text='{"action":"fix","file":"core_candidate.py"}')

    runner = CoreRunner()
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(2), _check(0), _check(0)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == SUCCESS_CLEAN
    assert result.code_path.read_text(encoding="utf-8") == (
        "from manim import *\n\nclass Solution(Scene):\n    def construct(self):\n        self.wait(2)\n"
    )
    assert runner.runs == 1
    round_usage = _read_json(result.evidence_dir / "round_01" / "usage.json")
    assert round_usage["compose_report_path"] == "round_01/compose_report.json"
    assert round_usage["core_diff_path"] == "round_01/core_diff.patch"
    assert round_usage["full_diff_path"] == "round_01/full_diff.patch"
    assert "self.wait(2)" in (result.evidence_dir / "round_01" / "core_diff.patch").read_text(encoding="utf-8")


def test_repair_layout_full_candidate_mode_uses_public_bundle_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code = (
        "from manim import *\n\n"
        "class Solution(Scene):\n"
        "    def construct(self):\n"
        "        self.wait()\n"
    )
    bundle = _write_case(tmp_path, job_id="full-view", code=code)
    bundle.candidate_mode = "full"

    class FullRunner:
        name = "full_runner"

        def run(self, workdir: Path, prompt: str, budget: Budget):
            assert f"Read {workdir / 'candidate.py'} once" in prompt
            assert not (workdir / "core_candidate.py").exists()
            (workdir / "candidate.py").write_text(code.replace("wait()", "wait(2)"), encoding="utf-8")
            from libs.quality_repair.schemas import AgentRunReport

            return AgentRunReport(changed=True, tokens_used=111, final_text='{"action":"fix","file":"candidate.py"}')

    _force_sdk_runner(monkeypatch, FullRunner())
    checker = StubChecker([_check(2), _check(0), _check(0)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == SUCCESS_CLEAN
    assert "self.wait(2)" in result.code_path.read_text(encoding="utf-8")


def test_deterministic_layout_prepatch_disabled_and_sdk_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 99\n", tokens_per_run=321)
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(2), _check(0), _check(0)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == SUCCESS_CLEAN
    assert result.code_path != bundle.code_path
    assert result.code_path.read_text(encoding="utf-8") == "x = 99\n"
    assert result.rounds_used == 1
    assert result.tokens_used == 321
    assert runner.runs == 1
    assert "deterministic_clean" not in result.reasons
    manifest = _read_json(result.evidence_dir / "bundle_manifest.json")
    assert manifest["deterministic_layout_prepatch"]["enabled"] is False
    assert manifest["deterministic_layout_prepatch"]["accepted"] is False
    assert manifest["deterministic_layout_prepatch"]["reasons"] == ["disabled_agent_only_mode"]


def test_layout_risk_only_context_goes_to_agent_no_fix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    code_path = tmp_path / "candidate.py"
    code_path.write_text("x = 1\n", encoding="utf-8")
    layout_context = _write_json(
        tmp_path / "layout_context.json",
        {
            "active_visible_objects": [
                {"path": "line", "class": "Line", "kind": "shape", "bbox": {"center_x": 0, "center_y": 0}},
                {"path": "label", "class": "MathTex", "kind": "formula", "text": "A_1", "bbox": {"center_x": 1, "center_y": 0}},
            ],
            "top_blocking_issues": [
                {
                    "category": "label_shape_overlap_risk",
                    "ratio_of_smaller": 0.9,
                    "a": {"path": "line", "class": "Line", "kind": "shape", "bbox": {"center_x": 0, "center_y": 0}},
                    "b": {"path": "label", "class": "MathTex", "kind": "formula", "text": "A_1", "bbox": {"center_x": 1, "center_y": 0}},
                }
            ],
            "blocking_layout_issue_count": 1,
            "pass": False,
            "status": "layout_failed",
            "safe_area": {"x_min": -7.1, "x_max": 7.1, "y_min": -4, "y_max": 4},
        },
    )
    bundle = RepairBundle(job_id="risk-only", code_path=code_path, layout_context=layout_context, evidence_root=tmp_path / "evidence")
    runner = FakeRunner(final_text='{"action":"no_fix","severity":"risk_only","confidence":0.91}', tokens_per_run=99)
    _force_sdk_runner(monkeypatch, runner)

    current_label_risk = CheckResult(
        ok=True,
        passed=False,
        blocking_count=1,
        issues=[
            {
                "category": "label_shape_overlap_risk",
                "a": {"path": "line", "class": "Line", "kind": "shape", "bbox": {"center_x": 0, "center_y": 0}},
                "b": {"path": "label", "class": "MathTex", "kind": "formula", "text": "A_1", "bbox": {"center_x": 1, "center_y": 0}},
            }
        ],
    )

    result = repair(bundle, ToolBox(checker=StubChecker([current_label_risk])))

    assert result.status == REPAIR_UNCHANGED
    assert result.code_path == bundle.code_path
    assert result.rounds_used == 1
    assert result.tokens_used == 99
    assert runner.runs == 1
    assert "agent_no_fix" in result.reasons
    manifest = _read_json(result.evidence_dir / "bundle_manifest.json")
    assert manifest["layout_actionability"]["sdk_actionable_blocking_count"] == 0
    assert manifest["layout_actionability"]["controller_policy"] == "hint_only_agent_decides"
    decision = _read_json(result.evidence_dir / "round_01" / "agent_decision.json")
    assert decision["action"] == "no_fix"


def test_stale_contract_degrades_to_sdk_when_deterministic_prepatch_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 99\n")
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(1, a="Ghost", b="B"), _check(0), _check(0)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == SUCCESS_CLEAN
    assert result.rounds_used == 1
    assert result.tokens_used == 1000
    assert runner.runs == 1
    manifest = _read_json(result.evidence_dir / "bundle_manifest.json")
    assert manifest["deterministic_layout_prepatch"]["enabled"] is False
    assert manifest["contract"]["ok"] is not False


def test_sdk_starts_from_original_check_when_deterministic_prepatch_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 3\n", tokens_per_run=321)
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(2), _check(0), _check(0)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == SUCCESS_CLEAN
    assert result.code_path != bundle.code_path
    assert result.code_path.read_text(encoding="utf-8") == "x = 3\n"
    assert result.rounds_used == 1
    assert result.tokens_used == 321
    assert runner.runs == 1
    manifest = _read_json(result.evidence_dir / "bundle_manifest.json")
    assert manifest["deterministic_layout_prepatch"]["enabled"] is False
    assert manifest["deterministic_layout_prepatch"]["accepted"] is False
    assert manifest["deterministic_layout_prepatch"]["after_blocking"] == 2


def test_sdk_round_usage_uses_original_blocking_when_deterministic_prepatch_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_case(tmp_path)
    bundle.budget = Budget(max_rounds=1, no_progress_stop=1)
    runner = FakeRunner(new_code="x = 4\n", tokens_per_run=222)
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(5), _check(4), _check(4)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == "SUCCESS_DEGRADED"
    assert result.code_path.read_text(encoding="utf-8") == "x = 4\n"
    assert result.before["blocking_count"] == 5
    assert result.after["blocking_count"] == 4
    assert runner.runs == 1
    round_usage = _read_json(result.evidence_dir / "round_01" / "usage.json")
    assert round_usage["before_blocking"] == 5
    assert round_usage["after_blocking"] == 4
    assert round_usage["accepted"] is True


def test_repair_worse_rolls_back_externally(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 99\n")
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(1), _check(0), _check(3)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == REPAIR_UNCHANGED
    assert result.code_path == bundle.code_path
    assert result.code_path.read_text(encoding="utf-8") == "x = 1\n"
    assert "repair_worse_rolled_back" in result.reasons
    acceptance = _read_json(result.evidence_dir / "acceptance.json")
    summary = _read_json(result.evidence_dir / "summary.json")
    assert acceptance["status"] == "REPAIR_WORSE"
    assert summary["worsened"] is True
    assert summary["changed"] is False


def test_repair_rejected_round_writes_attempted_diff_and_after_check_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 99\n")
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(1), _check(3)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == REPAIR_UNCHANGED
    assert result.code_path == bundle.code_path
    assert result.code_path.read_text(encoding="utf-8") == "x = 1\n"
    round_dir = result.evidence_dir / "round_01"
    usage = _read_json(round_dir / "usage.json")
    assert usage["attempted_changed"] is True
    assert usage["accepted"] is False
    assert usage["before_blocking"] == 1
    assert usage["after_blocking"] == 3
    assert usage["rejected_diff_path"] == "round_01/rejected_diff.patch"
    rejected_diff = round_dir / "rejected_diff.patch"
    assert rejected_diff.exists()
    assert "x = 99" in rejected_diff.read_text(encoding="utf-8")
    check_after = _read_json(round_dir / "check_after" / "check_result.json")
    assert check_after["blocking_count"] == 3
    assert check_after["passed"] is False
    assert check_after["issues"] == [{"kind": "overlap", "a": "A", "b": "B"}]
    assert check_after["signature"] == usage["signature"]
    assert check_after["error"] is None


def test_stale_layout_object_references_degrade_to_sdk_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 2\n")
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(1, a="Ghost", b="B"), _check(0), _check(0)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == SUCCESS_CLEAN
    assert result.code_path.read_text(encoding="utf-8") == "x = 2\n"
    assert runner.runs == 1
    assert "stale_object_references" in result.reasons
    manifest = _read_json(result.evidence_dir / "bundle_manifest.json")
    assert manifest["contract"]["ok"] is True
    assert "missing_object:Ghost" in manifest["contract"]["warnings"]


def test_runner_error_without_edit_is_classified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(error="claude_sdk_result_error:Reached maximum number of turns")
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(1)])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == REPAIR_UNCHANGED
    assert result.code_path == bundle.code_path
    assert "runner_error_no_edit" in result.reasons
    usage = _read_json(result.evidence_dir / "round_01" / "usage.json")
    assert usage["error_class"] == "runner_error_no_edit"
    assert usage["error"] == "claude_sdk_result_error:Reached maximum number of turns"


def test_check_error_after_edit_is_classified_and_keeps_attempted_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _write_case(tmp_path)
    runner = FakeRunner(new_code="x = 99\n")
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([_check(1), CheckResult.failure("layout_probe_crashed")])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == REPAIR_UNCHANGED
    assert result.code_path == bundle.code_path
    assert "check_error_after_edit" in result.reasons
    round_dir = result.evidence_dir / "round_01"
    usage = _read_json(round_dir / "usage.json")
    assert usage["error_class"] == "check_error_after_edit"
    assert usage["attempted_changed"] is True
    assert "x = 99" in (round_dir / "rejected_diff.patch").read_text(encoding="utf-8")


def test_detect_only_logic_skips_agent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = _write_case(tmp_path, job_id="logic-1")
    logic_contract = _write_json(
        tmp_path / "logic_contract.json",
        {"kind": "slope_text_proof", "expected_value": 2},
    )
    bundle.profile = "logic"
    bundle.logic_contract = logic_contract
    runner = FakeRunner(new_code="x = 2\n")
    _force_sdk_runner(monkeypatch, runner)
    checker = StubChecker([CheckResult(ok=True, passed=False, blocking_count=1, issues=[])])

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == REPAIR_UNCHANGED
    assert result.repairability == "detect_only"
    assert runner.runs == 0
    assert "kind_not_whitelisted:slope_text_proof" in result.reasons


def test_missing_sdk_fails_open_with_default_runner(tmp_path: Path, monkeypatch) -> None:
    bundle = _write_case(tmp_path)
    checker = StubChecker([_check(1)])
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", None)

    result = repair(bundle, ToolBox(checker=checker))

    assert result.status == REPAIR_UNCHANGED
    assert result.code_path == bundle.code_path
    assert "runner_error" in result.reasons


def test_toolbox_rejects_custom_runner_public_api(tmp_path: Path) -> None:
    checker = StubChecker([_check(1)])
    runner = FakeRunner(new_code="x = 2\n")

    with pytest.raises(TypeError):
        ToolBox(checker=checker, runner=runner)  # type: ignore[call-arg]


def test_top_level_cli_bundle_clean_case(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "case"
    bundle_dir.mkdir()
    (bundle_dir / "candidate.py").write_text("x = 1\n", encoding="utf-8")
    checker_script = bundle_dir / "checker.py"
    checker_script.write_text(
        "import json\nprint(json.dumps({'passed': True, 'blocking_count': 0, 'issues': []}))\n",
        encoding="utf-8",
    )
    _write_json(
        bundle_dir / "tool_config.json",
        {"check_cmd": [sys.executable, str(checker_script), "--code", "{code}"]},
    )

    proc = subprocess.run(
        [sys.executable, "-m", "quality_repair", "--bundle", str(bundle_dir)],
        cwd=Path(__file__).resolve().parents[3],
        capture_output=True,
        text=True,
        check=False,
    )

    payload = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert payload["status"] == REPAIR_UNCHANGED
    assert payload["code_path"] == str(bundle_dir / "candidate.py")
    assert Path(payload["evidence_dir"]).exists()
