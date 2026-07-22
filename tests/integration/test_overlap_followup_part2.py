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



def test_materialized_followup_requires_evidence_continuity(
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

    def discontinuous(bundle, toolbox):
        del toolbox
        second_dir = request.evidence_root / bundle.job_id
        second_code = second_dir / "workdir" / "candidate.py"
        second_code.parent.mkdir(parents=True)
        second_code.write_text(BASE_CODE.replace("ORIGIN", "DOWN"), encoding="utf-8")
        return api.RepairResult(
            status="SUCCESS_CLEAN",
            code_path=second_code,
            before={"blocking_count": 4},
            after={"blocking_count": 0},
            rounds_used=1,
            tokens_used=500,
            evidence_dir=second_dir,
            reasons=[],
        )

    monkeypatch.setattr(api, "repair", discontinuous)
    result = backend.repair_core_followup(request, object(), first)

    assert result.status == "SUCCESS_DEGRADED"
    assert result.code_path == first_code
    assert result.after["blocking_count"] == 5
    assert result.tokens_used == 10_500
    assert "followup_failed_best_preserved" in result.reasons
    assert "followup_evidence_discontinuity" in result.reasons
