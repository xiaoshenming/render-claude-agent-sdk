"""Cross-field consistency for figure Reviewer structured output."""

from __future__ import annotations

from collections.abc import Mapping

REPAIR_ACTIONS = {"auto_repair", "evidence_only", "human_review"}


def validate_figure_output_consistency(value: Mapping[str, object]) -> None:
    # Free-form diagnosis can explain the absence of auto_repair. Only structured
    # issues drive repair actions; the caller derives decision from those actions.
    issues = value.get("issues", ())
    actions = {item.get("repair_action") for item in issues if isinstance(item, dict)}
    if not actions <= REPAIR_ACTIONS:
        raise ValueError("invalid figure fidelity repair_action")
    for item in issues:
        if (
            item.get("repair_action") == "auto_repair"
            and item.get("confidence", 0) < 0.85
        ):
            raise ValueError("auto_repair requires confidence >= 0.85")
