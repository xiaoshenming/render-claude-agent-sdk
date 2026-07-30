import json

from manim_quality.assurance.models import AssuranceCase
from manim_quality.assurance.tools import (
    inspect_code_review,
    inspect_execution,
    inspect_layout,
)
from manim_quality.assurance.tts import (
    _effectively_silent,
    _narration_comparison,
)


def test_effective_silence_uses_audible_threshold() -> None:
    assert _effectively_silent("-inf")
    assert _effectively_silent("-91.0")
    assert not _effectively_silent("-12.5")


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


def test_code_review_detects_wrong_derived_function_coefficient(tmp_path) -> None:
    source = tmp_path / "main.py"
    source.write_text(
        """
def make_mini_fig(center, label, k_val, b_val, kb_val):
    return k_val, b_val, kb_val

make_mini_fig(None, "A", -0.6, 0.3, -0.8)
""",
        encoding="utf-8",
    )
    sample = case(tmp_path)
    sample = AssuranceCase(
        key=sample.key,
        question=sample.question,
        human_tags=sample.human_tags,
        expected_verdict=sample.expected_verdict,
        video_path=sample.video_path,
        log_dir=sample.log_dir,
        source_path=source,
    )

    report = inspect_code_review(sample)

    assert report.status == "risk"
    assert report.risk_codes == ("derived_function_parameter_mismatch",)
    mismatch = report.evidence[0]["derived_parameter_mismatches"][0]
    assert mismatch["expected"] == -0.18
    assert mismatch["actual"] == -0.8


def test_narration_comparison_matches_source_and_subtitle(tmp_path) -> None:
    source = tmp_path / "main.py"
    subtitle = tmp_path / "final.srt"
    source.write_text(
        "scene.voiceover(text='三角形ABC是等边三角形')\n",
        encoding="utf-8",
    )
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:03,000\n三角形ABC是等边三角形\n",
        encoding="utf-8",
    )

    result = _narration_comparison(source, subtitle)

    assert result["verified"] is True
    assert result["similarity"] == 1.0
