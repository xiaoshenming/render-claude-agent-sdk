import pytest

from manim_quality.assurance.contracts import validate_assurance_output
from manim_quality.contracts._json_values import freeze_json_object


def test_output_requires_every_tool_receipt() -> None:
    value = {
        "status": "review",
        "summary": "发现最终产物风险",
        "tool_receipts": [
            {"tool": name, "status": "complete", "evidence_ids": ["e-1"]}
            for name in (
                "inspect_artifact",
                "inspect_execution",
                "inspect_code_review",
                "inspect_layout",
                "inspect_risk_frames",
                "inspect_tts",
                "inspect_consistency",
            )
        ],
        "issues": [],
    }

    validate_assurance_output(value)
    validate_assurance_output(freeze_json_object(value, "output"))


def test_pass_rejects_missing_or_risky_evidence() -> None:
    value = {
        "status": "pass",
        "summary": "错误地通过",
        "tool_receipts": [],
        "issues": [{"severity": "high", "category": "layout"}],
    }

    with pytest.raises(ValueError, match="required tool"):
        validate_assurance_output(value)
