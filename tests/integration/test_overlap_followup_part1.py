from pathlib import Path

import pytest

from manim_quality.layout.adapter import OverlapAdapter
from manim_quality.layout.policy import ResidualRiskPolicy
from manim_quality.layout.result_mapping import OverlapDisposition

from .overlap_support import (
    BASE_CODE,
    make_check,
    make_request,
    vendor_result,
)



def test_five_round_budget_rechecks_no_edit_before_full_candidate_fallback(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api
    edited = BASE_CODE.replace("label.move_to(ORIGIN)", "label.shift(UP)")

    class RunnerFactory:
        calls = 0

        def __call__(self, **kwargs):
            del kwargs
            self.calls += 1
            if self.calls == 1:

                class NoEditRunner:
                    name = "no_edit_runner"

                    def run(self, workdir: Path, prompt: str, budget):
                        del workdir, prompt, budget
                        return api.AgentRunReport(
                            changed=False,
                            tokens_used=1_000,
                            error="claude_sdk_result_error:no edit",
                        )

                return NoEditRunner()

            class FullCandidateRunner:
                name = "full_candidate_runner"

                def run(self, workdir: Path, prompt: str, budget):
                    del prompt, budget
                    assert not (workdir / "core_candidate.py").exists()
                    (workdir / "candidate.py").write_text(edited, encoding="utf-8")
                    return api.AgentRunReport(
                        changed=True,
                        tokens_used=500,
                        final_text='{"action":"fix","file":"candidate.py"}',
                    )

            return FullCandidateRunner()

    factory = RunnerFactory()
    monkeypatch.setattr(api.api_module, "ClaudeSDKRunner", factory)
    checker = api.StubChecker(
        [make_check(api, 5), make_check(api, 5), make_check(api, 0)]
    )

    result = OverlapAdapter(backend).repair(
        make_request(tmp_path, tokens=30_000), checker
    )

    assert result.disposition is OverlapDisposition.CANDIDATE_RECHECK_REQUIRED
    assert result.after_blocking == 0
    assert result.code_path.read_text(encoding="utf-8") == edited
    assert factory.calls == 2


def test_semantic_safe_progress_can_use_one_bounded_core_followup(
    tmp_path: Path,
) -> None:
    request = make_request(tmp_path, tokens=80_000)
    first_dir = request.evidence_root / "first"
    second_dir = request.evidence_root / "second"
    first_code = first_dir / "workdir" / "candidate.py"
    second_code = second_dir / "workdir" / "candidate.py"
    first_code.parent.mkdir(parents=True)
    second_code.parent.mkdir(parents=True)
    first_code.write_text(BASE_CODE.replace("ORIGIN", "UP"), encoding="utf-8")
    second_code.write_text(BASE_CODE.replace("ORIGIN", "DOWN"), encoding="utf-8")
    first = vendor_result(
        status="SUCCESS_DEGRADED",
        candidate=first_code,
        before=8,
        after=5,
        tokens=10_000,
        evidence_dir=first_dir,
    )
    second = vendor_result(
        status="SUCCESS_CLEAN",
        candidate=second_code,
        before=8,
        after=0,
        tokens=20_000,
        evidence_dir=second_dir,
    )

    class Backend:
        followups = 0

        def repair(self, request, checker):
            del request, checker
            return first

        def repair_core_followup(self, request, checker, previous):
            del request, checker
            assert previous is first
            self.followups += 1
            return second

    backend = Backend()
    result = OverlapAdapter(
        backend, policy=ResidualRiskPolicy(second_attempt_min_tokens=60_000)
    ).repair(request, object())

    assert result.disposition is OverlapDisposition.CANDIDATE_RECHECK_REQUIRED
    assert result.code_path == second_code
    assert backend.followups == 1


def test_second_attempt_exception_preserves_first_attempt_usage(tmp_path: Path) -> None:
    request = make_request(tmp_path, tokens=80_000)
    first_dir = request.evidence_root / "first"
    first_code = first_dir / "workdir" / "candidate.py"
    first_code.parent.mkdir(parents=True)
    first_code.write_text(BASE_CODE.replace("ORIGIN", "UP"), encoding="utf-8")
    first = vendor_result(
        status="SUCCESS_DEGRADED",
        candidate=first_code,
        before=8,
        after=5,
        tokens=10_000,
        evidence_dir=first_dir,
    )

    class Backend:
        def repair(self, request, checker):
            del request, checker
            return first

        def repair_core_followup(self, request, checker, previous):
            del request, checker, previous
            raise RuntimeError("second attempt failed")

    result = OverlapAdapter(Backend()).repair(request, object())

    assert result.disposition is OverlapDisposition.RESIDUAL_CANDIDATE_RECHECK_REQUIRED
    assert result.code_path == first_code
    assert result.tokens_used == 10_000
    assert result.rounds_used == 1
    assert result.evidence_dir == first_dir
    assert "previous_best_preserved" in result.reasons


def test_materialized_core_followup_maps_first_candidate_and_remaining_budget(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api
    request = make_request(tmp_path, tokens=80_000)
    first_dir = request.evidence_root / request.job_id
    first_code = first_dir / "workdir" / "candidate.py"
    first_code.parent.mkdir(parents=True)
    first_code.write_text(BASE_CODE.replace("ORIGIN", "UP"), encoding="utf-8")
    first = api.RepairResult(
        status="SUCCESS_DEGRADED",
        code_path=first_code,
        repairability="auto_ready",
        before={"blocking_count": 8},
        after={"blocking_count": 5},
        rounds_used=1,
        tokens_used=10_000,
        evidence_dir=first_dir,
        reasons=[],
    )
    captured = {}

    def capture(bundle, toolbox):
        del toolbox
        captured["bundle"] = bundle
        second_dir = request.evidence_root / bundle.job_id
        second_code = second_dir / "workdir" / "candidate.py"
        second_code.parent.mkdir(parents=True)
        second_code.write_text(BASE_CODE.replace("ORIGIN", "DOWN"), encoding="utf-8")
        return api.RepairResult(
            status="SUCCESS_CLEAN",
            code_path=second_code,
            repairability="auto_ready",
            before={"blocking_count": 5},
            after={"blocking_count": 0},
            rounds_used=1,
            tokens_used=20_000,
            evidence_dir=second_dir,
            reasons=[],
        )

    monkeypatch.setattr(api, "repair", capture)
    result = backend.repair_core_followup(request, object(), first)

    bundle = captured["bundle"]
    assert bundle.code_path == first_code
    assert bundle.layout_context == request.layout_context_path
    assert bundle.candidate_mode == "core"
    assert bundle.budget.max_rounds == 4
    assert bundle.budget.token_hard_cap == 2**63 - 1
    assert result.before["blocking_count"] == 8
    assert result.after["blocking_count"] == 0
    assert result.rounds_used == 2
    assert result.tokens_used == 30_000


def test_materialized_followup_rejects_negative_usage_without_masking(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api
    request = make_request(tmp_path, tokens=80_000)
    first_dir = request.evidence_root / request.job_id
    first_code = first_dir / "workdir" / "candidate.py"
    first_code.parent.mkdir(parents=True)
    first_code.write_text(BASE_CODE.replace("ORIGIN", "UP"), encoding="utf-8")
    first = api.RepairResult(
        status="SUCCESS_DEGRADED",
        code_path=first_code,
        repairability="auto_ready",
        before={"blocking_count": 8},
        after={"blocking_count": 5},
        rounds_used=1,
        tokens_used=10_000,
        evidence_dir=first_dir,
        reasons=[],
    )

    def invalid(bundle, toolbox):
        del toolbox
        second_dir = request.evidence_root / bundle.job_id
        second_dir.mkdir(parents=True)
        return api.RepairResult(
            status="SUCCESS_CLEAN",
            code_path=first_code,
            before={"blocking_count": 4},
            after={"blocking_count": 0},
            rounds_used=1,
            tokens_used=-500,
            evidence_dir=second_dir,
            reasons=[],
        )

    monkeypatch.setattr(api, "repair", invalid)
    result = backend.repair_core_followup(request, object(), first)

    assert result.status == "SUCCESS_DEGRADED"
    assert result.code_path == first_code
    assert result.after["blocking_count"] == 5
    assert result.tokens_used == 10_000
    assert result.rounds_used == 2
    assert "followup_failed_best_preserved" in result.reasons
    assert "followup_usage_invalid" in result.reasons
