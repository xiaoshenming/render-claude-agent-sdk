from pathlib import Path

import anyio

from manim_quality.assurance.models import AssuranceCase, ToolReport
from manim_quality.assurance.toolset import AssuranceToolset


def test_bound_tool_ignores_model_echoed_case_key(tmp_path: Path) -> None:
    case = AssuranceCase(
        key="authoritative-case",
        question="test",
        video_path=tmp_path / "video.mp4",
        log_dir=tmp_path,
    )
    toolset = AssuranceToolset(case, tmp_path)
    tool = next(
        grant for grant in toolset.grants() if grant.name == "inspect_code_review"
    )

    result = anyio.run(tool.execute, {"case_key": "model-echo-typo"})

    assert result.status == "ok"
    assert "inspect_code_review" in toolset.reports
    assert toolset.reports["inspect_code_review"].tool == "inspect_code_review"


def test_receipt_fields_are_bound_to_observed_tool_report(tmp_path: Path) -> None:
    case = AssuranceCase(
        key="authoritative-case",
        question="test",
        video_path=tmp_path / "video.mp4",
        log_dir=tmp_path,
    )
    toolset = AssuranceToolset(case, tmp_path)
    toolset.reports["inspect_consistency"] = ToolReport(
        tool="inspect_consistency",
        status="risk",
        risk_codes=("identity_mismatch",),
        evidence=(
            {"id": "authoritative-case:consistency"},
            {"id": "authoritative-case:artifact-identity"},
        ),
    )

    normalized = toolset.normalize_output({
        "tool_receipts": [{
            "tool": "inspect_consistency",
            "status": "complete",
            "evidence_ids": ["authoritative-case:consistency"],
        }],
    })

    assert normalized["tool_receipts"] == [{
        "tool": "inspect_consistency",
        "status": "risk",
        "evidence_ids": [
            "authoritative-case:consistency",
            "authoritative-case:artifact-identity",
        ],
    }]
