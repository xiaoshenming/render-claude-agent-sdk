"""Normalize provider-specific native Reviewer results without blocking."""

from manim_quality.contracts._json_values import thaw_json_object

from .figure_fidelity import _decision as figure_decision
from .figure_fidelity import _normalize_actions as normalize_figure_actions
from .figure_fidelity import _validate_output as validate_figure_output


def ordered_results(results, specs, model):
    by_name = {str(item.get("agent_type")): item for item in results}
    rows = []
    for spec in specs:
        item = thaw_json_object(by_name[spec.name])
        metadata = item.get("sdk_metadata")
        observed = metadata.get("tool_uses") if isinstance(metadata, dict) else None
        if observed != len(spec.allowed_tools):
            item["protocol_warnings"] = [
                f"native_tool_count:{observed!r}/{len(spec.allowed_tools)}"
            ]
        payload = item["payload"]
        if spec.name == "figure_fidelity_reviewer":
            raw = item["raw_payload"]
            warnings = raw.get("coverage", {}).get("protocol_warnings", [])
            if "unstructured_output_preserved" not in warnings:
                try:
                    validate_figure_output(raw)
                except (TypeError, ValueError) as error:
                    payload = {**payload, "decision": "needs_repair"}
                    item.setdefault("protocol_warnings", []).append(
                        f"figure_payload_nonstandard:{error}"
                    )
                else:
                    payload = raw
                    item["action_normalizations"] = normalize_figure_actions(
                        payload["issues"]
                    )
                    payload["decision"] = figure_decision(payload["issues"])
        item["payload"] = payload
        item.update({"usage": None, "usage_complete": True, "model": model})
        rows.append(item)
    return tuple(rows)
