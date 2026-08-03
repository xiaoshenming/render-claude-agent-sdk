from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .contracts import validate_assurance_output

POLICY_VERSION = "final-assurance-policy-v1"
POLICY_RULES = (
    "derived_parameter_mismatch_promoted",
    "confirmed_anchor_drift_promoted",
)


@dataclass(frozen=True, slots=True)
class RawAgentAssessment:
    output: dict[str, object]


@dataclass(frozen=True, slots=True)
class PolicyAdjustedAssessment:
    output: dict[str, object]
    policy_version: str
    policy_sha256: str
    change_reasons: tuple[str, ...]
    raw_sha256: str
    adjusted_sha256: str


def apply_assurance_policy(
    raw: RawAgentAssessment,
    reports: dict[str, object],
    case_key: str,
) -> PolicyAdjustedAssessment:
    output = json.loads(json.dumps(raw.output, ensure_ascii=False))
    reasons = []
    if _normalize_derived_parameters(output, reports, case_key):
        reasons.append("derived_parameter_mismatch_promoted")
    if _normalize_anchor_drift(output):
        reasons.append("confirmed_anchor_drift_promoted")
    expected = {
        name: report
        for name, report in reports.items()
        if isinstance(report, dict)
    }
    validate_assurance_output(output, expected_reports=expected)
    return PolicyAdjustedAssessment(
        output=output,
        policy_version=POLICY_VERSION,
        policy_sha256=POLICY_SHA256,
        change_reasons=tuple(reasons),
        raw_sha256=_sha(raw.output),
        adjusted_sha256=_sha(output),
    )


def _normalize_derived_parameters(output, reports, case_key) -> bool:
    evidence = reports.get("inspect_code_review", {}).get("evidence", [])
    mismatches = evidence[0].get("derived_parameter_mismatches", []) if evidence else []
    if not mismatches or not isinstance(output.get("issues"), list):
        return False
    changed = False
    evidence_ids = [f"{case_key}:final-source"]
    if reports.get("inspect_risk_frames", {}).get("evidence"):
        evidence_ids.append(f"{case_key}:risk-frames")
    for mismatch in mismatches:
        expected, actual = mismatch.get("expected"), mismatch.get("actual")
        match = next(
            (
                row
                for row in output["issues"]
                if str(expected) in str(row.get("summary"))
                and str(actual) in str(row.get("summary"))
            ),
            None,
        )
        if match is None:
            summary = (
                f"函数图像派生系数错误：实际 {actual}，应为 {expected}。"
            )
            output["issues"].append(
                {
                    "severity": "high",
                    "category": "function_visualization",
                    "summary": summary,
                    "evidence_ids": evidence_ids,
                }
            )
        else:
            match["severity"] = "high"
            match["evidence_ids"] = list(
                dict.fromkeys([*match.get("evidence_ids", []), *evidence_ids])
            )
        changed = True
    if output.get("status") != "incomplete":
        output["status"] = "review"
    return changed


def _normalize_anchor_drift(output) -> bool:
    changed = False
    for issue in output.get("issues", []):
        summary = str(issue.get("summary", ""))
        ids = issue.get("evidence_ids", [])
        confirmed = any(str(item).endswith(":risk-frames") for item in ids)
        drift_terms = ("漂移", "脱离", "悬空", "旧坐标")
        if confirmed and any(term in summary for term in drift_terms):
            changed |= issue.get("severity") != "high"
            issue["severity"] = "high"
    return changed


def _sha(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode()).hexdigest()


POLICY_SHA256 = _sha({"version": POLICY_VERSION, "rules": POLICY_RULES})
