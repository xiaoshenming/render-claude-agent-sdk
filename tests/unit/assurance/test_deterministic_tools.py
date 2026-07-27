import json

from manim_quality.assurance.models import AssuranceCase
from manim_quality.assurance.tools import (
    inspect_code_review,
    inspect_execution,
    inspect_layout,
)


def case(tmp_path) -> AssuranceCase:
    logs = tmp_path / "logs"
    logs.mkdir()
    return AssuranceCase(
        key="CASE-001",
        question="test",
        human_tags=("overlap",),
        expected_verdict="命中但未交付",
        video_path=tmp_path / "video.mp4",
        log_dir=logs,
    )


def test_execution_detects_missing_final_submission(tmp_path) -> None:
    sample = case(tmp_path)
    (sample.log_dir / "run_summary.json").write_text(
        json.dumps({"decision": "HOLD", "final_revision_id": None}),
        encoding="utf-8",
    )

    report = inspect_execution(sample)

    assert report.status == "risk"
    assert "missing_final_revision" in report.risk_codes


def test_review_and_layout_preserve_structured_findings(tmp_path) -> None:
    sample = case(tmp_path)
    (sample.log_dir / "findings.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "finding_id": "logic-1",
                        "category": "logic",
                        "severity": "blocking",
                        "summary": "wrong answer",
                    },
                    {
                        "finding_id": "layout-1",
                        "category": "layout",
                        "severity": "blocking",
                        "summary": "overlap",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    assert inspect_code_review(sample).risk_codes == ("blocking_logic_finding",)
    assert inspect_layout(sample).risk_codes == ("blocking_layout_finding",)
