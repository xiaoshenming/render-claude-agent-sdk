"""Build compact layout repair brief and contract payloads."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from libs.quality_repair.contract.workdir_format import _object_ref
from libs.quality_repair.contract.workdir_normalize import _normalize_layout_context

from tools.quality_repair_checkers.layout_repair_brief_geometry import (
    average_ratio,
    blocking_count,
    case_id_from_path,
    center,
    estimated_tokens,
    file_size,
    has_shape,
    has_textual,
    is_label_shape_issue,
    is_textual_pair,
    issue_objects,
    issue_ratio,
    issue_region,
    issues_from_context,
    looks_like_same_origin_stack,
    looks_like_step_panel_lifecycle,
    object_text,
    same_center,
    share,
    time_window,
    truncate,
)

HIGH_CONFIDENCE_SAME_ROUND_THRESHOLD = 0.7
ACTIONABLE_LABEL_SHAPE_RATIO_THRESHOLD = 0.65


def build_layout_repair_brief(
    layout_ctx: dict[str, Any],
    *,
    case_id: str | None = None,
    source_path: Path | None = None,
) -> dict[str, Any]:
    normalized = _normalize_layout_context(layout_ctx) or {}
    raw_issues = issues_from_context(normalized)
    raw_blocking = blocking_count(normalized, raw_issues)
    actionable_issues, ignored_issues = _split_sdk_actionable_issues(raw_issues)
    hidden_issue_count = max(0, raw_blocking - len(raw_issues))
    sdk_actionable_count = len(actionable_issues) + hidden_issue_count
    active = normalized.get("active_visible_objects")
    active_objects = active if isinstance(active, list) else []
    full_bytes = file_size(source_path)
    clusters = _build_clusters(actionable_issues)
    ignored_reason_counts = Counter(str(issue.get("reason") or "ignored") for issue in ignored_issues)
    primary = clusters[0]["failure_type"] if clusters else "no_blocking_layout_issue"
    confidence = clusters[0]["confidence"] if clusters else 1.0
    if sdk_actionable_count == 0 and raw_blocking > 0:
        primary = "no_sdk_actionable_layout_issue"
    return {
        "schema_version": "quality_repair.layout_repair_brief.v1",
        "case_id": case_id or case_id_from_path(source_path),
        "status": str(normalized.get("status") or ("layout_failed" if raw_issues else "pass")),
        "pass": bool(normalized.get("pass", normalized.get("passed", not raw_issues))),
        "blocking_count": sdk_actionable_count,
        "raw_blocking_count": raw_blocking,
        "sdk_actionable_blocking_count": sdk_actionable_count,
        "ignored_issue_count": len(ignored_issues),
        "ignored_reason_counts": dict(sorted(ignored_reason_counts.items())),
        "hidden_issue_count": hidden_issue_count,
        "input_stats": {
            "full_json_bytes": full_bytes,
            "active_object_count": len(active_objects),
            "issue_count": len(raw_issues),
            "actionable_issue_count": len(actionable_issues),
            "ignored_issue_count": len(ignored_issues),
            "hidden_issue_count": hidden_issue_count,
            "full_estimated_tokens": estimated_tokens(full_bytes),
        },
        "summary": {
            "primary_failure_type": primary,
            "primary_confidence": confidence,
            "cluster_count": len(clusters),
            "raw_blocking_count": raw_blocking,
            "sdk_actionable_blocking_count": sdk_actionable_count,
            "ignored_issue_count": len(ignored_issues),
            "ignored_reason_counts": dict(sorted(ignored_reason_counts.items())),
            "recommended_default_input": "layout_repair_brief.json + layout_repair_contract.json",
            "full_context_policy": "fallback_only",
        },
        "clusters": clusters,
        "ignored_issues": ignored_issues[:20],
        "fallback_policy": {
            "read_full_layout_context_only_if": [
                "primary_confidence < 0.55",
                "all contract patches are unsafe",
                "outer validation says repair made layout worse",
            ],
            "default_behavior": "Do not feed full layout_context.json to SDK by default.",
        },
    }


def build_layout_repair_contract(brief: dict[str, Any]) -> dict[str, Any]:
    clusters = brief.get("clusters") if isinstance(brief.get("clusters"), list) else []
    same_round_cluster_ids = _same_round_cluster_ids(brief, clusters)
    sdk_actionable_count = _sdk_actionable_count(brief)
    if sdk_actionable_count <= 0:
        return {
            "schema_version": "quality_repair.layout_repair_contract.v1",
            "case_id": brief.get("case_id"),
            "blocking_count": 0,
            "raw_blocking_count": brief.get("raw_blocking_count", brief.get("blocking_count")),
            "sdk_actionable_blocking_count": 0,
            "active_cluster_policy": {
                "default": "no_sdk_actionable_repair",
                "primary_cluster_id": None,
                "same_round_cluster_ids": [],
                "secondary_cluster_rule": "Only risk/artifact issues remain; do not spend SDK turns on layout edits.",
            },
            "default_read_order": ["layout_repair_brief.json", "layout_repair_contract.json"],
            "after_default_read_order_action": "Do not edit candidate.py for risk-only layout evidence. Leave it unchanged.",
            "full_context_policy": brief.get("fallback_policy", {}),
            "clusters": [],
            "ignored_issue_count": brief.get("ignored_issue_count", 0),
        }
    return {
        "schema_version": "quality_repair.layout_repair_contract.v1",
        "case_id": brief.get("case_id"),
        "blocking_count": sdk_actionable_count,
        "raw_blocking_count": brief.get("raw_blocking_count", brief.get("blocking_count")),
        "sdk_actionable_blocking_count": sdk_actionable_count,
        "ignored_issue_count": brief.get("ignored_issue_count", 0),
        "active_cluster_policy": {
            "default": "repair_all_high_confidence_clusters" if same_round_cluster_ids else "repair_priority_1_only",
            "primary_cluster_id": _primary_cluster_id(clusters),
            "same_round_cluster_ids": sorted(same_round_cluster_ids),
            "secondary_cluster_rule": _secondary_cluster_rule(same_round_cluster_ids),
        },
        "default_read_order": ["layout_repair_brief.json", "layout_repair_contract.json"],
        "after_default_read_order_action": "Read candidate.py if needed, then make the smallest safe Edit; do not keep rereading context without editing.",
        "full_context_policy": brief.get("fallback_policy", {}),
        "clusters": [_contract_cluster(cluster, same_round_cluster_ids=same_round_cluster_ids) for cluster in clusters if isinstance(cluster, dict)],
    }


def build_layout_issue_digest(
    layout_ctx: dict[str, Any],
    *,
    case_id: str | None = None,
    source_path: Path | None = None,
) -> dict[str, Any]:
    """Build the issue-only input used by the layout SDK agent."""
    normalized = _normalize_layout_context(layout_ctx) or {}
    raw_issues = issues_from_context(normalized)
    raw_blocking = blocking_count(normalized, raw_issues)
    return {
        "schema_version": "quality_repair.layout_issue_digest.issue_only.v1",
        "case_id": case_id or case_id_from_path(source_path),
        "status": str(normalized.get("status") or ("layout_failed" if raw_blocking else "pass")),
        "pass": bool(normalized.get("pass", normalized.get("passed", raw_blocking == 0))),
        "blocking_layout_issue_count": raw_blocking,
        "issue_count": len(raw_issues),
        "issues": [_full_issue_row(issue, index) for index, issue in enumerate(raw_issues, 1)],
    }


def build_agent_safety_contract() -> dict[str, Any]:
    """Build the safety/acceptance contract for the exploratory Agent."""
    return {
        "schema_version": "quality_repair.agent_safety_contract.v1",
        "editable_files": ["candidate.py"],
        "tool_policy": {
            "allowed_tools": ["Read", "Edit"],
            "forbidden_tools": ["Agent", "Task", "Bash", "Write", "Grep", "Glob", "WebSearch", "WebFetch"],
            "use_relative_paths_only": True,
            "direct_full_context_read": "forbidden",
        },
        "forbidden": [
            "change_math_or_text_strings",
            "change_voiceover_text",
            "delete_teaching_content_to_reduce_overlap",
            "write_case_specific_rules",
            "edit_files_other_than_candidate_py",
            "read_facts_layout_context_full_json_directly",
        ],
        "must_preserve": [
            "MathTex/Text string literals",
            "voiceover(text=...) content",
            "Chinese wording and problem text",
            "mathematical meaning",
            "teaching order and animation intent",
        ],
        "acceptance": {
            "must_compile": True,
            "checker_must_not_get_worse": True,
            "string_literals_must_be_preserved": True,
            "worse_patch_must_rollback": True,
            "agent_cannot_self_accept": True,
        },
        "evidence_policy": {
            "default_input": ["layout_issue_digest.json"],
            "legacy_aliases": {
                "layout_repair_brief.json": "layout_issue_digest.json",
            },
            "full_context": "read_only_via_local_detail_queries",
            "query_budget": {
                "max_requests_per_round": 3,
                "max_output_bytes_per_request": 12288,
                "same_target_once_per_round": True,
                "max_consecutive_evidence_only_rounds": 2,
            },
        },
    }


def _sdk_actionable_count(brief: dict[str, Any]) -> int:
    for key in ("sdk_actionable_blocking_count", "blocking_count"):
        value = brief.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _full_issue_row(issue: dict[str, Any], index: int) -> dict[str, Any]:
    row = dict(issue)
    row.setdefault("issue_id", f"I{index:03d}")
    return row


def _digest_issue_index(issues: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    return [_digest_issue(issue, index) for index, issue in enumerate(issues[:limit], 1)]


def _digest_issue(issue: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "issue_id": f"I{index:03d}",
        "step": issue.get("step"),
        "category": issue.get("category") or issue.get("kind") or issue.get("type"),
        "region": issue_region(issue),
        "ratio": round(issue_ratio(issue), 4),
        "x_overlap": _round_if_number(issue.get("x_overlap")),
        "y_overlap": _round_if_number(issue.get("y_overlap")),
        "time": time_window(issue),
        "objects": [_digest_object(obj, include_bbox=False) for obj in issue_objects(issue)],
    }


def _digest_object(obj: Any, *, include_bbox: bool = True) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {"object_id": str(obj)}
    obj_center = center(obj)
    row = {
        "object_id": _object_ref(obj),
        "class": obj.get("class"),
        "kind": obj.get("kind"),
        "text": truncate(object_text(obj), 80),
    }
    if obj_center:
        row["center"] = [round(obj_center[0], 3), round(obj_center[1], 3)]
    bbox = obj.get("bbox")
    if include_bbox and isinstance(bbox, dict):
        row["bbox"] = {
            key: _round_if_number(bbox.get(key))
            for key in ("left", "right", "top", "bottom", "width", "height", "center_x", "center_y")
            if bbox.get(key) is not None
        }
    return {key: value for key, value in row.items() if value not in (None, "", {})}


def _digest_object_index(normalized: dict[str, Any], issues: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    objects: list[Any] = []
    active = normalized.get("active_visible_objects")
    if isinstance(active, list):
        objects.extend(active)
    for issue in issues:
        objects.extend(issue_objects(issue))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for obj in objects:
        row = _digest_object(obj, include_bbox=False)
        object_id = str(row.get("object_id") or "")
        key = object_id or json_dumps_compact(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def _digest_group(cluster: dict[str, Any], issue_index: list[dict[str, Any]]) -> dict[str, Any]:
    evidence = cluster.get("evidence") if isinstance(cluster.get("evidence"), list) else []
    return {
        "group_id": cluster.get("cluster_id"),
        "issue_count": cluster.get("issue_count"),
        "region": cluster.get("affected_region"),
        "failure_type_hint": cluster.get("failure_type"),
        "confidence_hint": cluster.get("confidence"),
        "stats": cluster.get("stats") if isinstance(cluster.get("stats"), dict) else {},
        "signals": _signals_for_cluster(cluster),
        "source_hints": _source_hints_for_cluster(cluster),
        "representative_issue_ids": _representative_issue_ids(evidence, issue_index),
        "representative_collisions": evidence[:2],
    }


def _signals_for_cluster(cluster: dict[str, Any]) -> list[str]:
    failure_type = str(cluster.get("failure_type") or "")
    mapping = {
        "step_panel_lifecycle_accumulation": ["same_region_repeated_across_later_steps", "old_and_new_panel_visible_together"],
        "same_origin_text_stack": ["multiple_text_objects_share_center", "same_step_default_origin_stack"],
        "label_shape_overlap": ["text_label_intersects_shape_bbox", "label_buff_or_direction_may_be_too_small"],
    }
    return mapping.get(failure_type, ["layout_overlap_needs_agent_judgment"])


def _source_hints_for_cluster(cluster: dict[str, Any]) -> list[str]:
    failure_type = str(cluster.get("failure_type") or "")
    if failure_type == "step_panel_lifecycle_accumulation":
        return ["step_panel", "problem_panel", "make_step_panel", "make_problem_panel", "place_panel", "current_step_panel"]
    if failure_type == "label_shape_overlap":
        return ["make_point_label", "avoid_overlap", "next_to", "buff"]
    if failure_type == "same_origin_text_stack":
        return ["VGroup", "arrange", "next_to", "self.add"]
    return ["VGroup", "arrange", "next_to", "shift", "scale"]


def _representative_issue_ids(evidence: list[Any], issue_index: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        for row in issue_index:
            if _evidence_matches_issue(item, row):
                issue_id = str(row.get("issue_id"))
                if issue_id not in ids:
                    ids.append(issue_id)
                break
    return ids


def _evidence_matches_issue(evidence: dict[str, Any], issue: dict[str, Any]) -> bool:
    if evidence.get("step") != issue.get("step"):
        return False
    if str(evidence.get("category") or "") != str(issue.get("category") or ""):
        return False
    evidence_texts = {str(obj.get("text") or "") for obj in evidence.get("objects", []) if isinstance(obj, dict)}
    issue_texts = {str(obj.get("text") or "") for obj in issue.get("objects", []) if isinstance(obj, dict)}
    return bool(evidence_texts & issue_texts) or not evidence_texts


def _visible_object_count(normalized: dict[str, Any]) -> int:
    active = normalized.get("active_visible_objects")
    return len(active) if isinstance(active, list) else 0


def _dominant_regions(issues: list[dict[str, Any]], *, limit: int = 3) -> list[str]:
    regions = Counter(issue_region(issue) for issue in issues)
    return [region for region, _ in regions.most_common(limit)]


def _time_span(issues: list[dict[str, Any]]) -> list[float] | None:
    values: list[float] = []
    for issue in issues:
        window = time_window(issue)
        if not isinstance(window, dict):
            continue
        for key in ("start", "end", "recommended_timestamp"):
            value = window.get(key)
            if value is None or isinstance(value, bool):
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                pass
    return [round(min(values), 3), round(max(values), 3)] if values else None


def _round_if_number(value: Any) -> Any:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return value


def json_dumps_compact(value: Any) -> str:
    from json import dumps

    return dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _split_sdk_actionable_issues(issues: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    actionable: list[dict[str, Any]] = []
    ignored: list[dict[str, Any]] = []
    suppress_label_shape_risk = _has_dominant_lifecycle_signal(issues)
    for issue in issues:
        reason = _non_actionable_reason(issue, suppress_label_shape_risk=suppress_label_shape_risk)
        if reason:
            row = _evidence_row(issue)
            row["reason"] = reason
            ignored.append(row)
        else:
            actionable.append(issue)
    return actionable, ignored


def _has_dominant_lifecycle_signal(issues: list[dict[str, Any]]) -> bool:
    if len(issues) < 8:
        return False
    text_issues = [issue for issue in issues if is_textual_pair(issue)]
    panel = [issue for issue in text_issues if issue_region(issue) == "right_panel"]
    return len(panel) >= 8 and len(panel) / len(issues) >= 0.5 and looks_like_step_panel_lifecycle(text_issues)


def _non_actionable_reason(issue: dict[str, Any], *, suppress_label_shape_risk: bool = False) -> str | None:
    category = str(issue.get("category") or issue.get("kind") or issue.get("type") or "").lower()
    if "label_shape" in category:
        if "risk" in category and (
            suppress_label_shape_risk
            or _has_zero_axis_overlap(issue)
            or issue_ratio(issue) < ACTIONABLE_LABEL_SHAPE_RATIO_THRESHOLD
        ):
            return "label_shape_overlap_risk"
        return None
    if "frame_bounds_overflow" in category:
        return "frame_bounds_overflow_risk"
    if _has_zero_axis_overlap(issue):
        return "non_intersecting_bbox_risk"
    if has_shape(issue) and has_textual(issue) and not is_textual_pair(issue) and issue_ratio(issue) < ACTIONABLE_LABEL_SHAPE_RATIO_THRESHOLD:
        return "shape_text_proximity_risk"
    if _has_oversized_bbox_artifact(issue):
        return "oversized_bbox_artifact"
    return None


def _has_zero_axis_overlap(issue: dict[str, Any]) -> bool:
    return _non_positive_numeric(issue.get("x_overlap")) or _non_positive_numeric(issue.get("y_overlap"))


def _non_positive_numeric(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(value) <= 0
    except (TypeError, ValueError):
        return False


def _has_oversized_bbox_artifact(issue: dict[str, Any]) -> bool:
    return any(_bbox_width(obj) >= 14.0 or _bbox_height(obj) >= 8.0 for obj in issue_objects(issue))


def _bbox_width(obj: Any) -> float:
    bbox = obj.get("bbox") if isinstance(obj, dict) else None
    if not isinstance(bbox, dict):
        return 0.0
    try:
        if bbox.get("width") is not None:
            return abs(float(bbox["width"]))
        return abs(float(bbox["right"]) - float(bbox["left"]))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _bbox_height(obj: Any) -> float:
    bbox = obj.get("bbox") if isinstance(obj, dict) else None
    if not isinstance(bbox, dict):
        return 0.0
    try:
        if bbox.get("height") is not None:
            return abs(float(bbox["height"]))
        return abs(float(bbox["top"]) - float(bbox["bottom"]))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _contract_cluster(cluster: dict[str, Any], *, same_round_cluster_ids: set[str]) -> dict[str, Any]:
    failure_type = str(cluster.get("failure_type") or "generic_layout_overlap")
    cluster_id = str(cluster.get("cluster_id") or "")
    return {
        "cluster_id": cluster.get("cluster_id"),
        "failure_type": failure_type,
        "priority": cluster.get("priority"),
        "confidence": cluster.get("confidence"),
        "affected_region": cluster.get("affected_region"),
        "repair_scope": _repair_scope(cluster, same_round_cluster_ids, cluster_id),
        "must_fix": _must_fix(failure_type),
        "must_preserve": [
            "Preserve all MathTex/Text string content.",
            "Preserve voiceover(text=...) strings and teaching order.",
            "Preserve scene class name, custom_services imports, colors, and animation intent.",
        ],
        "forbidden_edits": [
            "Do not delete important teaching content just to reduce overlap.",
            "Do not branch on case_id, exact object path, exact formula text, or sample-specific coordinates.",
            "Do not read layout_context.full.json unless fallback policy allows it.",
        ],
        "preferred_patch": _preferred_patch(failure_type),
        "fallback": "If a safe minimal edit is not obvious, leave candidate.py unchanged and explain why.",
    }


def _same_round_cluster_ids(brief: dict[str, Any], clusters: list[Any]) -> set[str]:
    try:
        blocking = int(brief.get("blocking_count") or 0)
    except (TypeError, ValueError):
        return set()
    if blocking <= 0 or blocking > 3:
        return set()
    high_confidence_ids = {
        str(cluster.get("cluster_id"))
        for cluster in clusters
        if isinstance(cluster, dict)
        and cluster.get("cluster_id")
        and _cluster_confidence(cluster) >= HIGH_CONFIDENCE_SAME_ROUND_THRESHOLD
    }
    return high_confidence_ids if len(high_confidence_ids) >= 2 else set()


def _cluster_confidence(cluster: dict[str, Any]) -> float:
    try:
        return float(cluster.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _secondary_cluster_rule(same_round_cluster_ids: set[str]) -> str:
    if same_round_cluster_ids:
        return "blocking_count <= 3: repair priority 1 and all high-confidence secondary clusters in the same SDK round when a safe local patch is obvious; otherwise keep the fail-open fallback."
    return "Do not spend the first Edit on secondary clusters. Use them only if the primary cluster is already fixed or impossible to edit safely."


def _repair_scope(cluster: dict[str, Any], same_round_cluster_ids: set[str], cluster_id: str) -> str:
    if cluster_id in same_round_cluster_ids:
        return "active_same_round"
    return "active_first_edit" if int(cluster.get("priority") or 0) == 1 else "background_only_until_primary_improves"


def _primary_cluster_id(clusters: list[Any]) -> Any:
    for cluster in clusters:
        if isinstance(cluster, dict) and int(cluster.get("priority") or 0) == 1:
            return cluster.get("cluster_id")
    return None


def _build_clusters(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not issues:
        return []
    remaining = list(issues)
    buckets = _cluster_buckets(remaining)
    clusters = [_make_cluster(failure_type, cluster_issues, 0) for failure_type, cluster_issues in buckets]
    clusters = sorted(clusters, key=_cluster_sort_key)
    clusters = _promote_dominant_lifecycle_cluster(clusters, total_issues=len(issues))
    for priority, cluster in enumerate(clusters, 1):
        cluster["priority"] = priority
        cluster["cluster_id"] = f"C{priority:02d}"
    return clusters


def _promote_dominant_lifecycle_cluster(clusters: list[dict[str, Any]], *, total_issues: int) -> list[dict[str, Any]]:
    if total_issues <= 0:
        return clusters
    for index, cluster in enumerate(clusters):
        if str(cluster.get("failure_type") or "") != "step_panel_lifecycle_accumulation":
            continue
        issue_count = int(cluster.get("issue_count") or 0)
        confidence = _cluster_confidence(cluster)
        if issue_count >= 8 and issue_count / total_issues >= 0.5 and confidence >= 0.7:
            return [cluster] + clusters[:index] + clusters[index + 1 :]
    return clusters


def _cluster_buckets(remaining: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    buckets: list[tuple[str, list[dict[str, Any]]]] = []
    label = [issue for issue in remaining if is_label_shape_issue(issue)]
    if label:
        buckets.append(("label_shape_overlap", label))
        remaining = [issue for issue in remaining if issue not in label]
    text_issues = [issue for issue in remaining if is_textual_pair(issue)]
    panel = _step_panel_lifecycle_issues(text_issues)
    if panel:
        buckets.append(("step_panel_lifecycle_accumulation", panel))
        remaining = [issue for issue in remaining if issue not in panel]
    same_origin = [issue for issue in remaining if is_textual_pair(issue) and same_center(issue)]
    if looks_like_same_origin_stack(same_origin):
        buckets.append(("same_origin_text_stack", same_origin))
        remaining = [issue for issue in remaining if issue not in same_origin]
    if remaining:
        buckets.append(("generic_layout_overlap", remaining))
    return buckets


def _step_panel_lifecycle_issues(text_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    panel = [issue for issue in text_issues if issue_region(issue) == "right_panel"]
    if panel and looks_like_step_panel_lifecycle(text_issues):
        return panel
    return [issue for issue in panel if _is_small_right_panel_lifecycle_issue(issue)]


def _is_small_right_panel_lifecycle_issue(issue: dict[str, Any]) -> bool:
    if not _is_later_step(issue):
        return False
    category = str(issue.get("category") or issue.get("kind") or issue.get("type") or "").lower()
    if "text_formula" not in category and not _has_text_formula_pair(issue):
        return False
    return _has_text_formula_pair(issue)


def _is_later_step(issue: dict[str, Any]) -> bool:
    value = issue.get("step")
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(value) > 1
    except (TypeError, ValueError):
        return False


def _has_text_formula_pair(issue: dict[str, Any]) -> bool:
    objects = issue_objects(issue)
    if len(objects) < 2:
        return False
    return any(_is_plain_text_object(obj) for obj in objects[:2]) and any(_is_formula_object(obj) for obj in objects[:2])


def _is_plain_text_object(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    kind = str(obj.get("kind") or "").lower()
    cls = str(obj.get("class") or "")
    return kind == "text" or cls in {"Text", "MarkupText", "Paragraph"}


def _is_formula_object(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    kind = str(obj.get("kind") or "").lower()
    cls = str(obj.get("class") or "")
    return kind in {"formula", "mathtex", "tex"} or cls in {"MathTex", "Tex"}


def _make_cluster(failure_type: str, issues: list[dict[str, Any]], priority: int) -> dict[str, Any]:
    categories = Counter(str(issue.get("category") or issue.get("kind") or issue.get("type") or "issue") for issue in issues)
    regions = Counter(issue_region(issue) for issue in issues)
    steps = sorted({issue.get("step") for issue in issues if issue.get("step") is not None}, key=str)
    texts = sorted({object_text(obj) for issue in issues for obj in issue_objects(issue) if object_text(obj)})
    refs = sorted({_object_ref(obj) or "" for issue in issues for obj in issue_objects(issue) if isinstance(obj, dict)})
    affected_region = regions.most_common(1)[0][0] if regions else "unknown"
    return {
        "cluster_id": f"C{priority:02d}",
        "priority": priority,
        "failure_type": failure_type,
        "confidence": _confidence(failure_type, issues, categories, regions, steps, texts, refs),
        "issue_count": len(issues),
        "affected_region": affected_region,
        "root_cause": _root_cause(failure_type, affected_region),
        "stats": _cluster_stats(categories, regions, steps, texts, refs, issues),
        "evidence": _representative_evidence(issues),
    }


def _cluster_stats(categories: Counter[str], regions: Counter[str], steps: list[Any], texts: list[str], refs: list[str], issues: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "dominant_category": categories.most_common(1)[0][0] if categories else None,
        "dominant_category_share": share(categories),
        "dominant_region_share": share(regions),
        "unique_steps": len(steps),
        "unique_texts": len(texts),
        "unique_objects": len([ref for ref in refs if ref]),
        "average_ratio": average_ratio(issues),
    }


def _confidence(failure_type: str, issues: list[dict[str, Any]], categories: Counter[str], regions: Counter[str], steps: list[Any], texts: list[str], refs: list[str]) -> float:
    category_score = share(categories)
    region_score = share(regions)
    ratio_score = min(1.0, average_ratio(issues))
    if failure_type == "step_panel_lifecycle_accumulation":
        step_score = min(1.0, len(steps) / 4.0)
        object_score = min(1.0, max(len(texts) / 6.0, len([ref for ref in refs if ref]) / 8.0))
    elif failure_type == "same_origin_text_stack":
        step_score = 1.0 if len(steps) <= 2 else max(0.2, 2.0 / max(1, len(steps)))
        object_score = min(1.0, len([ref for ref in refs if ref]) / 5.0)
    elif failure_type == "label_shape_overlap":
        step_score = 1.0
        object_score = 1.0 if any(has_shape(issue) and has_textual(issue) for issue in issues) else 0.5
    else:
        step_score = min(1.0, max(1, len(steps)) / 4.0)
        object_score = min(1.0, len([ref for ref in refs if ref]) / 8.0)
    value = 0.25 * category_score + 0.25 * region_score + 0.20 * step_score + 0.20 * object_score + 0.10 * ratio_score
    return round(min(0.99, max(0.05, value)), 2)


def _representative_evidence(issues: list[dict[str, Any]], *, limit: int = 2) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, str]] = set()
    for issue in sorted(issues, key=lambda item: (-issue_ratio(item), str(item.get("step", "")))):
        refs = [_object_ref(obj) or "" for obj in issue_objects(issue) if isinstance(obj, dict)]
        key = (issue.get("step"), refs[0] if refs else "", refs[1] if len(refs) > 1 else "")
        if key in seen:
            continue
        seen.add(key)
        selected.append(_evidence_row(issue))
        if len(selected) >= limit:
            break
    return selected


def _evidence_row(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "step": issue.get("step"),
        "category": issue.get("category") or issue.get("kind") or issue.get("type"),
        "ratio": round(issue_ratio(issue), 4),
        "region": issue_region(issue),
        "time": time_window(issue),
        "objects": [_evidence_object(obj) for obj in issue_objects(issue)],
    }


def _evidence_object(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {"ref": str(obj)}
    evidence = {"path": _object_ref(obj), "class": obj.get("class"), "kind": obj.get("kind"), "text": truncate(object_text(obj), 40)}
    obj_center = center(obj)
    if obj_center:
        evidence["center"] = [round(obj_center[0], 3), round(obj_center[1], 3)]
    return {key: value for key, value in evidence.items() if value not in (None, "")}


def _must_fix(failure_type: str) -> list[str]:
    mapping = {
        "same_origin_text_stack": ["把同一步骤里重叠的 Text/MathTex 放入 VGroup 后 arrange/next_to/shift。", "避免多个对象创建后直接 self.add(*items) 留在同一默认坐标。"],
        "step_panel_lifecycle_accumulation": ["在新 step_panel 出现前清理、替换或 FadeOut 旧 problem_panel/step_panel。", "优先复用 current_step_panel 或统一 helper，避免多组右侧推导面板同时可见。"],
        "label_shape_overlap": ["把点名、边名、角标等标签沿几何元素外侧轻微移开。", "优先使用 next_to/shift/buff 调整标签，不改变几何主结构。"],
        "generic_layout_overlap": ["基于 evidence 中的区域和对象类型做最小局部布局调整。", "优先增加 buff、缩放局部组、或移动局部文本块。"],
    }
    return mapping.get(failure_type, mapping["generic_layout_overlap"])


def _preferred_patch(failure_type: str) -> list[str]:
    mapping = {
        "same_origin_text_stack": ["VGroup(*texts).arrange(RIGHT or DOWN, buff=0.3-0.6)", "或对后续对象使用 next_to(previous, direction, buff=...)"],
        "step_panel_lifecycle_accumulation": ["self.play(FadeOut(previous_problem_panel_or_step_panel)) before showing next step_panel", "或 ReplacementTransform(previous_panel, next_panel)", "或 self.remove(previous_panel) when no animation is needed"],
        "label_shape_overlap": ["label.next_to(anchor_point_or_line, direction, buff=0.1-0.25)", "或 label.shift(vector) 只移动标签不移动图形"],
        "generic_layout_overlap": ["Increase local arrange buff or move the local VGroup away from the crowded region."],
    }
    return mapping.get(failure_type, mapping["generic_layout_overlap"])


def _root_cause(failure_type: str, region: str) -> str:
    mapping = {
        "same_origin_text_stack": f"{region} 中多个文字/公式对象中心点高度接近，像是未 arrange/next_to 就同时显示。",
        "step_panel_lifecycle_accumulation": f"{region} 中 problem_panel/step_panel 跨 later step 持续重叠，像是旧面板未清理导致右侧面板残留叠加。",
        "label_shape_overlap": f"{region} 中标签与几何图形/线段发生覆盖，像是标签锚点或 buff 过小。",
        "generic_layout_overlap": f"{region} 中存在布局重叠，但第一版规则未能稳定归入专门模式。",
    }
    return mapping.get(failure_type, mapping["generic_layout_overlap"])


def _priority_rank(failure_type: str) -> int:
    return {"label_shape_overlap": 1, "step_panel_lifecycle_accumulation": 2, "same_origin_text_stack": 3, "generic_layout_overlap": 9}.get(failure_type, 9)


def _cluster_sort_key(cluster: dict[str, Any]) -> tuple[float, int]:
    stats = cluster.get("stats") if isinstance(cluster.get("stats"), dict) else {}
    issue_count = float(cluster.get("issue_count") or 0)
    confidence = float(cluster.get("confidence") or 0)
    average = float(stats.get("average_ratio") or 0)
    rank_bonus = (10 - _priority_rank(str(cluster.get("failure_type") or ""))) * 0.03
    score = 2.0 * confidence + average + min(issue_count / 10.0, 1.0) * 0.8 + rank_bonus
    return (-score, _priority_rank(str(cluster.get("failure_type") or "")))
