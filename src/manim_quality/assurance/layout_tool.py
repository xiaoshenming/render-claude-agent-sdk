"""Final Assurance layout evidence tool."""

from __future__ import annotations

import json

from .lifecycle_evidence import (
    detached_transition_parts,
    persistent_result_placeholders,
)
from .models import AssuranceCase, ToolReport


def inspect_layout(case: AssuranceCase) -> ToolReport:
    detached = detached_transition_parts(case.source_path)
    placeholders = persistent_result_placeholders(case.source_path)
    lifecycle = (*detached, *placeholders)
    prior = _json(case.log_dir / "layout_evidence.json")
    if prior:
        evidence = {
            "id": f"{case.key}:quality-layout",
            "source": "quality_agent_reused_bbox",
            **prior,
            "lifecycle_findings": list(lifecycle),
        }
        if not prior.get("verified") or prior.get("error"):
            return _report(
                "incomplete",
                ("quality_layout_unverified",),
                evidence,
            )
        risks = _risk_codes(
            int(prior.get("blocking_count") or 0), detached, placeholders
        )
        return _report("risk" if risks else "complete", risks, evidence)
    findings = _findings(case)
    risks = _risk_codes(_blocking(findings), detached, placeholders)
    evidence = (
        (
            {
                "id": f"{case.key}:lifecycle-layout",
                "lifecycle_findings": list(lifecycle),
            },
        )
        if lifecycle
        else ()
    )
    return _report(
        "risk" if risks else ("complete" if findings else "incomplete"),
        risks,
        *evidence,
        *findings,
    )


def _risk_codes(blocking, detached, placeholders) -> tuple[str, ...]:
    risks = []
    if blocking:
        risks.append("blocking_layout_finding")
    if detached:
        risks.append("detached_transition_part")
    if placeholders:
        risks.append("persistent_result_placeholder")
    return tuple(risks)


def _findings(case: AssuranceCase) -> tuple[dict, ...]:
    rows = _json(case.log_dir / "findings.json").get("findings", [])
    if not isinstance(rows, list):
        return ()
    categories = {"layout", "overlap", "bbox"}
    return tuple(
        {"id": f"{case.key}:{row.get('finding_id', 'finding')}", **row}
        for row in rows
        if isinstance(row, dict) and str(row.get("category", "")).lower() in categories
    )


def _blocking(rows: tuple[dict, ...]) -> bool:
    return any(row.get("severity") in {"blocking", "critical", "high"} for row in rows)


def _report(status: str, risks: tuple[str, ...], *evidence) -> ToolReport:
    return ToolReport("inspect_layout", status, risks, tuple(evidence))


def _json(path) -> dict:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}
