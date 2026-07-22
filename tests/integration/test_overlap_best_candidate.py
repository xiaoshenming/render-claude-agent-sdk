from types import SimpleNamespace

from manim_quality.layout.policy import ResidualRiskPolicy
from manim_quality.layout.result_mapping import (
    OverlapDisposition,
    map_vendor_result,
)

from .overlap_support import BASE_CODE


def test_historical_best_candidate_survives_later_no_progress(tmp_path) -> None:
    original = tmp_path / "candidate.py"
    original.write_text(BASE_CODE, encoding="utf-8")
    best = tmp_path / "evidence" / "workdir" / "candidate.py"
    best.parent.mkdir(parents=True)
    best.write_text(
        BASE_CODE.replace("label.move_to(ORIGIN)", "label.shift(UP)"),
        encoding="utf-8",
    )
    observed = SimpleNamespace(
        status="REPAIR_UNCHANGED",
        code_path=original,
        before={"blocking_count": 3},
        after={"blocking_count": 2},
        rounds_used=2,
        tokens_used=200,
        cost_usd=0.0,
        evidence_dir=best.parents[1],
        reasons=["same_signature"],
    )

    result = map_vendor_result(
        observed,
        original_code_path=original,
        policy=ResidualRiskPolicy(),
    )

    assert result.disposition is OverlapDisposition.RESIDUAL_CANDIDATE_RECHECK_REQUIRED
    assert result.code_path == best
    assert "historical_best_candidate_preserved" in result.reasons


def test_verified_degraded_candidate_is_not_discarded_by_residual_threshold(
    tmp_path,
) -> None:
    original = tmp_path / "candidate.py"
    original.write_text(BASE_CODE, encoding="utf-8")
    best = tmp_path / "evidence" / "workdir" / "candidate.py"
    best.parent.mkdir(parents=True)
    best.write_text(
        BASE_CODE.replace("label.move_to(ORIGIN)", "label.shift(UP)"),
        encoding="utf-8",
    )
    observed = SimpleNamespace(
        status="SUCCESS_DEGRADED",
        code_path=best,
        before={"blocking_count": 42},
        after={"blocking_count": 19},
        rounds_used=3,
        tokens_used=900,
        cost_usd=0.0,
        evidence_dir=best.parents[1],
        reasons=["round_cap"],
    )

    result = map_vendor_result(
        observed,
        original_code_path=original,
        policy=ResidualRiskPolicy(),
    )

    assert result.disposition is OverlapDisposition.RESIDUAL_CANDIDATE_RECHECK_REQUIRED
    assert result.code_path == best
    assert result.after_blocking == 19
