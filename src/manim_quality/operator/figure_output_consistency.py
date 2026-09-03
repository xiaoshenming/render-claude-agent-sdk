"""Cross-field consistency for figure Reviewer structured output."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from manim_quality.agents._runtime_models import CorrectableOutputError


def validate_figure_output_consistency(value: Mapping[str, object]) -> None:
    issues = value.get("issues")
    rows = (
        [row for row in issues if isinstance(row, Mapping)]
        if isinstance(issues, Sequence) and not isinstance(issues, (str, bytes))
        else []
    )
    has_auto_repair = any(
        row.get("repair_action") == "auto_repair" for row in rows)
    diagnosis = str(value.get("diagnosis") or "").lower()
    diagnosis_claims_auto_repair = "auto_repair" in diagnosis
    if diagnosis_claims_auto_repair and not has_auto_repair:
        raise CorrectableOutputError(
            "diagnosis claims auto_repair but issues contain no auto_repair item"
        )
