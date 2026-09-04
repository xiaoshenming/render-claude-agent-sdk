"""Project executed tool facts without rewriting the model's issue judgments."""

from manim_quality.contracts._json_values import thaw_json_object

from .contracts import REQUIRED_TOOLS


def project_output(value, reports):
    payload = thaw_json_object(value)
    if REQUIRED_TOOLS <= reports.keys():
        # These facts belong to the runtime, including genuinely incomplete tools.
        payload["tool_receipts"] = [
            _receipt(name, reports[name]) for name in sorted(REQUIRED_TOOLS)
        ]
        issues = payload.get("issues")
        if isinstance(issues, list):
            statuses = {reports[name].status for name in REQUIRED_TOOLS}
            payload["status"] = (
                "incomplete" if "incomplete" in statuses
                else "review" if "risk" in statuses or issues else "pass"
            )
        return payload
    # Retain the existing partial normalization. Missing executions still fail
    # the original validator; no tool execution or semantic issue is invented.
    receipts = payload.get("tool_receipts")
    if isinstance(receipts, list):
        for receipt in receipts:
            if isinstance(receipt, dict) and receipt.get("tool") in reports:
                receipt.update(_receipt(receipt["tool"], reports[receipt["tool"]]))
    return payload


def _receipt(name, report):
    return {
        "tool": name,
        "status": report.status,
        "evidence_ids": [str(row["id"]) for row in report.evidence
                         if isinstance(row.get("id"), str)],
    }
