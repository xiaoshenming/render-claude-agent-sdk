from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def audit_holdout_manifest(manifest_csv: Path, runs_root: Path, *, min_count: int = 1) -> dict[str, Any]:
    manifest_csv = Path(manifest_csv)
    runs_root = Path(runs_root)
    candidate_ids = _read_manifest_sample_ids(manifest_csv)
    prior_seen = _read_prior_seen_samples(runs_root)
    eligible_ids = [sample_id for sample_id in candidate_ids if sample_id not in prior_seen]
    used_ids = [sample_id for sample_id in candidate_ids if sample_id in prior_seen]
    ok = len(eligible_ids) >= min_count
    return {
        "ok": ok,
        "reason": "ok"
        if ok
        else f"Not enough unseen holdout samples: required {min_count}, found {len(eligible_ids)}.",
        "manifest": str(manifest_csv),
        "runs_root": str(runs_root),
        "candidate_count": len(candidate_ids),
        "min_count": min_count,
        "prior_seen_count": len(used_ids),
        "eligible_count": len(eligible_ids),
        "eligible_sample_ids": eligible_ids,
        "prior_seen_sample_ids": used_ids,
        "prior_seen_samples": {sample_id: prior_seen[sample_id] for sample_id in used_ids},
    }


def write_holdout_audit(manifest_csv: Path, runs_root: Path, out_path: Path, *, min_count: int = 1) -> dict[str, Any]:
    result = audit_holdout_manifest(manifest_csv, runs_root, min_count=min_count)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _read_manifest_sample_ids(manifest_csv: Path) -> list[str]:
    rows = csv.DictReader(Path(manifest_csv).read_text(encoding="utf-8-sig").splitlines())
    sample_ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id or sample_id in seen:
            continue
        sample_ids.append(sample_id)
        seen.add(sample_id)
    return sample_ids


def _read_prior_seen_samples(runs_root: Path) -> dict[str, list[str]]:
    prior_seen: dict[str, list[str]] = {}
    if not runs_root.exists():
        return prior_seen
    for summary_path in sorted(runs_root.glob("*/summary.json")):
        summary = _read_json(summary_path)
        round_name = str(summary.get("round") or summary_path.parent.name)
        for sample_id in _sample_ids_from_summary(summary):
            prior_seen.setdefault(sample_id, []).append(round_name)
    return prior_seen


def _sample_ids_from_summary(summary: dict[str, Any]) -> list[str]:
    sample_ids: list[str] = []
    for case in summary.get("cases") or []:
        if not isinstance(case, dict):
            continue
        sample_id = str(case.get("sample_id") or "").strip()
        if sample_id:
            sample_ids.append(sample_id)
    return sample_ids


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
