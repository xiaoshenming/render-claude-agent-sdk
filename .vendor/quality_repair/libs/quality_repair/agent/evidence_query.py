"""Materialize scoped evidence files requested by the diagnostic agent."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas import SCHEMA_VERSION, read_json, write_json

DEFAULT_MAX_REQUESTS = 3
DEFAULT_MAX_OUTPUT_BYTES = 12_288
ALLOWED_QUERY_KINDS = {
    "full_bbox_by_issue_id",
    "object_lifecycle_by_object_id",
}


def materialize_evidence_requests(
    *,
    workdir: Path,
    round_no: int,
    requests: list[dict[str, Any]],
    max_requests: int = DEFAULT_MAX_REQUESTS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, Any]:
    """Write local evidence query results and return a structured report.

    This function may inspect full facts internally, but it only exposes bounded
    excerpts under evidence_queries/round_XX for the SDK to read next round.
    """
    out_dir = workdir / "evidence_queries" / f"round_{round_no:02d}"
    out_dir.mkdir(parents=True, exist_ok=True)
    budget = {
        "max_requests": max_requests,
        "max_output_bytes_per_request": max_output_bytes,
        "allowed_kinds": sorted(ALLOWED_QUERY_KINDS),
    }
    results: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    seen_targets: set[tuple[str, str]] = set()
    for index, request in enumerate(requests):
        request_id = _request_id(request, index)
        if index >= max_requests:
            denied.append({"request_id": request_id, "reason": "evidence_budget_request_count_exceeded"})
            continue
        kind = str(request.get("type") or request.get("kind") or "")
        if kind not in ALLOWED_QUERY_KINDS:
            denied.append({"request_id": request_id, "reason": f"evidence_query_kind_denied:{kind or 'missing'}"})
            continue
        target = _request_target(request)
        key = (kind, target)
        if key in seen_targets:
            denied.append({"request_id": request_id, "reason": f"duplicate_evidence_query:{kind}:{target}"})
            continue
        seen_targets.add(key)
        result = _run_request(workdir, request_id=request_id, kind=kind, request=request)
        file_path = out_dir / _result_filename(request_id, kind)
        write_report = _write_bounded(file_path, result, max_bytes=max_output_bytes)
        results.append(
            {
                "request_id": request_id,
                "ok": bool(result.get("ok")),
                "kind": kind,
                "file": _relative_query_path(file_path, workdir),
                "bytes": write_report["bytes"],
                "truncated": write_report["truncated"],
                "error": result.get("error"),
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "round": round_no,
        "results": results,
        "denied": denied,
        "budget": budget,
    }
    write_json(out_dir / "results.json", payload)
    return payload


def _run_request(workdir: Path, *, request_id: str, kind: str, request: dict[str, Any]) -> dict[str, Any]:
    if kind == "full_bbox_by_issue_id":
        return _full_bbox_by_issue_id(workdir, request_id=request_id, request=request)
    if kind == "object_lifecycle_by_object_id":
        return _object_lifecycle_by_object_id(workdir, request_id=request_id, request=request)
    if kind == "source_anchor_by_helper_name":
        return _source_anchor(workdir, request_id=request_id, kind=kind, needle=str(request.get("helper") or request.get("helper_name") or ""))
    if kind in {"source_anchor_by_text", "source_anchor_by_object_text"}:
        return _source_anchor(workdir, request_id=request_id, kind=kind, needle=str(request.get("text") or request.get("object_text") or ""))
    return {"request_id": request_id, "ok": False, "kind": kind, "error": "unsupported_evidence_query"}


def _full_bbox_by_issue_id(workdir: Path, *, request_id: str, request: dict[str, Any]) -> dict[str, Any]:
    issue_id = str(request.get("issue_id") or request.get("id") or "")
    issues = _layout_issues(_full_context(workdir))
    issue = _issue_by_id(issues, issue_id)
    if issue is None:
        return {"request_id": request_id, "ok": False, "kind": "full_bbox_by_issue_id", "issue_id": issue_id, "error": "issue_not_found"}
    return {
        "request_id": request_id,
        "ok": True,
        "kind": "full_bbox_by_issue_id",
        "issue_id": issue_id,
        "issue": issue,
    }


def _object_lifecycle_by_object_id(workdir: Path, *, request_id: str, request: dict[str, Any]) -> dict[str, Any]:
    object_id = str(request.get("object_id") or request.get("object_ref") or request.get("path") or request.get("name") or "")
    data = _full_context(workdir)
    objects = _matching_objects(data, object_id)
    appearances = []
    for issue_id, issue in _enumerate_issues(_layout_issues(data)):
        refs = [_object_ref(obj) for obj in _issue_objects(issue)]
        if object_id in refs:
            appearances.append(
                {
                    "issue_id": issue_id,
                    "category": issue.get("category") or issue.get("kind") or issue.get("type"),
                    "step": issue.get("step"),
                    "time_window": issue.get("time_window"),
                    "pair_refs": refs,
                    "ratio": issue.get("ratio_of_smaller", issue.get("overlap_ratio")),
                }
            )
    if not objects and not appearances:
        return {
            "request_id": request_id,
            "ok": False,
            "kind": "object_lifecycle_by_object_id",
            "object_id": object_id,
            "error": "object_not_found",
        }
    return {
        "request_id": request_id,
        "ok": True,
        "kind": "object_lifecycle_by_object_id",
        "object_id": object_id,
        "objects": objects[:8],
        "appearances": appearances[:40],
    }


def _source_anchor(workdir: Path, *, request_id: str, kind: str, needle: str) -> dict[str, Any]:
    if not needle.strip():
        return {"request_id": request_id, "ok": False, "kind": kind, "error": "source_anchor_empty_needle"}
    try:
        lines = (workdir / "candidate.py").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return {"request_id": request_id, "ok": False, "kind": kind, "error": f"candidate_unreadable:{exc}"}
    windows = _line_windows_for_needle(lines, needle)
    if not windows:
        return {"request_id": request_id, "ok": False, "kind": kind, "needle": needle, "error": "source_anchor_not_found"}
    return {
        "request_id": request_id,
        "ok": True,
        "kind": kind,
        "needle": needle,
        "windows": [
            {
                "start_line": start + 1,
                "end_line": end,
                "source": "\n".join(f"{index + 1}: {lines[index]}" for index in range(start, end)),
            }
            for start, end in windows
        ],
    }


def _full_context(workdir: Path) -> dict[str, Any]:
    for path in (workdir / "facts" / "layout_context.full.json", workdir / "facts" / "layout_context.json", workdir / "layout_context.json"):
        try:
            data = read_json(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return data
    return {}


def _layout_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("top_blocking_issues", "collisions", "blocking_pairs", "issues"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _issue_by_id(issues: list[dict[str, Any]], issue_id: str) -> dict[str, Any] | None:
    for generated_id, issue in _enumerate_issues(issues):
        if issue_id == generated_id or issue_id == str(issue.get("issue_id") or issue.get("id") or ""):
            return issue
    return None


def _enumerate_issues(issues: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    return [(f"I{index:03d}", issue) for index, issue in enumerate(issues, 1)]


def _matching_objects(data: dict[str, Any], object_id: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for key in ("active_visible_objects", "objects", "active_objects", "bboxes"):
        value = data.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _object_ref(item) == object_id:
                    matches.append(item)
        elif isinstance(value, dict):
            item = value.get(object_id)
            if isinstance(item, dict):
                matches.append(item)
    for issue in _layout_issues(data):
        for obj in _issue_objects(issue):
            if isinstance(obj, dict) and _object_ref(obj) == object_id:
                matches.append(obj)
    return _dedupe_objects(matches)


def _issue_objects(issue: dict[str, Any]) -> list[Any]:
    objects: list[Any] = []
    for key in ("a", "b", "object_a", "object_b", "a_raw", "b_raw"):
        value = issue.get(key)
        if value is not None:
            objects.append(value)
    return objects[:2]


def _object_ref(obj: Any) -> str:
    if not isinstance(obj, dict):
        return str(obj)
    for key in ("path", "id", "name", "ref"):
        value = obj.get(key)
        if value:
            return str(value)
    return ""


def _dedupe_objects(objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for obj in objects:
        key = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        result.append(obj)
    return result


def _line_windows_for_needle(lines: list[str], needle: str, *, radius: int = 12, limit: int = 4) -> list[tuple[int, int]]:
    hits = [index for index, line in enumerate(lines) if needle in line]
    windows: list[tuple[int, int]] = []
    for hit in hits[:limit]:
        start = max(0, hit - radius)
        end = min(len(lines), hit + radius + 1)
        windows.append((start, end))
    return windows


def _request_id(request: dict[str, Any], index: int) -> str:
    value = request.get("request_id") or request.get("id") or f"Q{index + 1:02d}"
    return _safe_component(str(value))


def _request_target(request: dict[str, Any]) -> str:
    for key in ("issue_id", "object_id", "object_ref", "path", "name", "helper", "helper_name", "text", "object_text"):
        value = request.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _result_filename(request_id: str, kind: str) -> str:
    suffix = ".md" if kind.startswith("source_anchor") else ".json"
    return f"{request_id}_{_safe_component(kind)}{suffix}"


def _safe_component(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)[:80] or "query"


def _relative_query_path(path: Path, workdir: Path) -> str:
    try:
        return path.relative_to(workdir).as_posix()
    except ValueError:
        return path.name


def _write_bounded(path: Path, payload: dict[str, Any], *, max_bytes: int) -> dict[str, Any]:
    if path.suffix == ".md":
        text = _payload_markdown(payload)
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    encoded = text.encode("utf-8")
    truncated = False
    if len(encoded) > max_bytes:
        preview = encoded[: max(0, max_bytes - 512)].decode("utf-8", errors="ignore")
        payload = {
            "request_id": payload.get("request_id"),
            "ok": payload.get("ok"),
            "kind": payload.get("kind"),
            "truncated": True,
            "preview": preview,
        }
        text = _payload_markdown(payload) if path.suffix == ".md" else json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        truncated = True
    path.write_text(text, encoding="utf-8")
    return {"bytes": path.stat().st_size, "truncated": truncated}


def _payload_markdown(payload: dict[str, Any]) -> str:
    lines = [f"# Evidence Query {payload.get('request_id', '')}", ""]
    for window in payload.get("windows", []) if isinstance(payload.get("windows"), list) else []:
        lines.extend(
            [
                f"## candidate.py lines {window.get('start_line')}-{window.get('end_line')}",
                "",
                "```python",
                str(window.get("source") or ""),
                "```",
                "",
            ]
        )
    if len(lines) <= 2:
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return "\n".join(lines).rstrip() + "\n"
