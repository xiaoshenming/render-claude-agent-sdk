from pathlib import Path
from types import SimpleNamespace

import pytest

from manim_quality.layout.adapter import OverlapAdapter
from manim_quality.layout.policy import ResidualRiskPolicy
from manim_quality.layout.result_mapping import OverlapDisposition

from .overlap_support import BASE_CODE, make_request, vendor_result


@pytest.mark.parametrize(
    ("residual", "reason", "tokens", "expected"),
    [
        (5, "runner_error_no_edit", 30_000, True),
        (2, "runner_error_no_edit", 30_000, False),
        (5, "check_error_after_edit", 30_000, False),
        (5, "runner_error_no_edit", 5_000, False),
    ],
)
def test_full_candidate_fallback_is_strictly_bounded(
    residual: int, reason: str, tokens: int, expected: bool
) -> None:
    policy = ResidualRiskPolicy(
        full_candidate_min_blocking=4,
        full_candidate_min_tokens=20_000,
    )

    assert (
        policy.allow_full_candidate_fallback(
            residual_blocking=residual,
            stop_reasons=(reason,),
            remaining_tokens=tokens,
            attempts_used=1,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("status", "before", "after"),
    [
        ("SUCCESS_CLEAN", 2, 1),
        ("SUCCESS_CLEAN", -1, 0),
        ("SUCCESS_DEGRADED", 4, 3),
        ("NOT_A_VENDOR_STATUS", 2, 0),
    ],
)
def test_inconsistent_vendor_success_fails_closed(
    tmp_path: Path, status: str, before: int, after: int
) -> None:
    request = make_request(tmp_path)
    candidate = request.evidence_root / request.job_id / "workdir" / "candidate.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(BASE_CODE.replace("ORIGIN", "UP"), encoding="utf-8")
    result = OverlapAdapter(
        SimpleNamespace(
            repair=lambda request, checker: vendor_result(
                status=status,
                candidate=candidate,
                before=before,
                after=after,
            )
        )
    ).repair(request, object())

    assert result.disposition is OverlapDisposition.REJECTED
    assert result.code_path == request.code_path


def test_vendor_candidate_path_escape_fails_closed(tmp_path: Path) -> None:
    request = make_request(tmp_path)
    outside = tmp_path / "outside.py"
    outside.write_text(BASE_CODE.replace("ORIGIN", "UP"), encoding="utf-8")
    vendor = vendor_result(
        status="SUCCESS_CLEAN",
        candidate=outside,
        before=2,
        after=0,
        evidence_dir=request.evidence_root / request.job_id,
    )
    vendor.evidence_dir.mkdir(parents=True)

    result = OverlapAdapter(SimpleNamespace(repair=lambda r, c: vendor)).repair(
        request, object()
    )

    assert result.disposition is OverlapDisposition.ERROR
    assert result.code_path == request.code_path
    assert "vendor_candidate_outside_evidence" in result.reasons


def test_vendor_usage_over_platform_budget_fails_closed(tmp_path: Path) -> None:
    request = make_request(tmp_path, tokens=500)
    candidate = request.evidence_root / request.job_id / "workdir" / "candidate.py"
    candidate.parent.mkdir(parents=True)
    candidate.write_text(BASE_CODE.replace("ORIGIN", "UP"), encoding="utf-8")
    vendor = vendor_result(
        status="SUCCESS_CLEAN", candidate=candidate, before=2, after=0, tokens=501
    )

    result = OverlapAdapter(SimpleNamespace(repair=lambda r, c: vendor)).repair(
        request, object()
    )

    assert result.disposition is OverlapDisposition.ERROR
    assert "vendor_usage_exceeds_remaining_budget" in result.reasons
    assert result.tokens_used == 501
    assert result.rounds_used == 1
    assert result.evidence_dir == vendor.evidence_dir


def test_vendor_exception_becomes_fail_closed_error(tmp_path: Path) -> None:
    request = make_request(tmp_path)

    def fail(request, checker):
        del request, checker
        raise RuntimeError("secret-bearing vendor failure")

    result = OverlapAdapter(SimpleNamespace(repair=fail)).repair(request, object())

    assert result.disposition is OverlapDisposition.ERROR
    assert result.code_path == request.code_path
    assert result.reasons == ("vendor_repair_error:RuntimeError",)
