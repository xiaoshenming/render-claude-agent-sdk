from __future__ import annotations

_FREEZE_TERMS = (
    "freeze", "frozen", "冻结", "静止", "卡顿", "停滞", "动画推进",
)


def normalize_detector_issues(
    output: dict[str, object],
    reports: dict[str, object],
    reviewers: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    """Downgrade unconfirmed detector findings without discarding evidence."""
    if not _core_reviewers_pass(reviewers):
        return ()
    medium_changed = False
    freeze_changed = False
    issues = output.get("issues")
    if not isinstance(issues, list):
        return ()
    for issue in issues:
        if not isinstance(issue, dict) or _has_reviewer_evidence(issue):
            continue
        if _is_freeze_telemetry(issue, reports):
            if issue.get("severity") in {"high", "medium"}:
                issue["severity"] = "warning"
                freeze_changed = True
            continue
        ids = [str(item) for item in issue.get("evidence_ids", [])]
        if (
            issue.get("severity") == "medium"
            and not any(item.endswith(":risk-frames") for item in ids)
        ):
            issue["severity"] = "warning"
            medium_changed = True
    reasons = []
    if medium_changed:
        reasons.append("unconfirmed_detector_medium_downgraded")
    if freeze_changed:
        reasons.append("unconfirmed_freeze_telemetry_downgraded")
    return tuple(reasons)


def _core_reviewers_pass(reviewers: tuple[dict[str, object], ...]) -> bool:
    decisions = {
        str(row.get("agent_type")): str(
            (row.get("payload") or {}).get("decision") or ""
        ).strip().lower()
        for row in reviewers if isinstance(row.get("payload"), dict)
    }
    core = {"math_geometry_reviewer", "animation_lifecycle_reviewer"}
    return core.issubset(decisions) and all(
        decisions[name] == "pass" for name in core
    )


def _has_reviewer_evidence(issue: dict) -> bool:
    return any(
        str(item).startswith("reviewer:")
        for item in issue.get("evidence_ids", [])
    )


def _is_freeze_telemetry(issue: dict, reports: dict[str, object]) -> bool:
    ids = [str(item) for item in issue.get("evidence_ids", [])]
    if not ids or not all(item.endswith(":risk-frames") for item in ids):
        return False
    text = " ".join((
        str(issue.get("category") or ""),
        str(issue.get("summary") or ""),
    )).lower()
    if not any(term in text for term in _FREEZE_TERMS):
        return False
    report = reports.get("inspect_risk_frames")
    if not isinstance(report, dict) or report.get("status") != "complete":
        return False
    if report.get("risk_codes"):
        return False
    evidence = report.get("evidence")
    first = evidence[0] if isinstance(evidence, list) and evidence else {}
    windows = first.get("windows") if isinstance(first, dict) else {}
    if not isinstance(windows, dict):
        return False
    return bool(windows.get("freeze")) and not bool(windows.get("black"))
