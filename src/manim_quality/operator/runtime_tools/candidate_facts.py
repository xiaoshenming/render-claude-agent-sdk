"""Keep geometric candidates intact; deduplicate identities, not meanings."""

from __future__ import annotations

import json
from collections.abc import Mapping

EVIDENCE_VERSION = "bbox-candidate-facts-v1"


def candidate_facts(probe: Mapping, classified: Mapping) -> dict[str, object]:
    rows = [row for key in (
        "semantic_row_overlaps", "top_overlaps", "top_bounds_violations",
    ) for row in probe.get(key, []) if isinstance(row, Mapping)]
    issues = [_normalize(row) for row in group_candidates(rows)]
    raw = dict(classified.get("raw") or {})
    raw.update(
        raw_issue_count=len(rows), candidate_count=len(issues),
        legacy_classified_issue_count=len(classified.get("issues") or []),
        snapshot_count=probe.get("snapshot_count"),
        estimated_duration=probe.get("estimated_duration"),
    )
    return {
        **classified, "issues": issues, "raw": raw,
        "evidence_only": True, "evidence_version": EVIDENCE_VERSION,
        "candidate_count": len(issues), "blocking_count": 0,
    }


def group_candidates(rows: list[Mapping]) -> list[dict]:
    groups: dict[str, dict] = {}
    for row in rows:
        identity = _identity(row)
        if identity not in groups:
            groups[identity] = dict(row)
            groups[identity]["occurrences"] = 1
            continue
        previous = groups[identity]
        window = _window(previous, row)
        count = previous["occurrences"] + 1
        if _score(row) > _score(previous):
            previous = dict(row)
        previous.update(time_window=window, occurrences=count)
        groups[identity] = previous
    return sorted(groups.values(), key=_score, reverse=True)


def _identity(row: Mapping) -> str:
    objects = []
    for key in ("a", "b", "object"):
        value = row.get(f"{key}_raw") or row.get(key)
        if isinstance(value, Mapping):
            objects.append({k: value.get(k) for k in ("path", "class", "kind", "text")})
        else:
            objects.append(value)
    # Same text in two different objects must remain two separate candidates.
    return json.dumps([row.get("scene"), row.get("category"), objects],
                      ensure_ascii=False, sort_keys=True)


def _normalize(row: Mapping) -> dict:
    result = dict(row)
    for key in ("a", "b", "object"):
        value = result.get(key)
        if isinstance(value, Mapping):
            result[f"{key}_raw"] = dict(value)
            result[key] = str(value.get("path") or value.get("text") or "")
    return result


def _window(first: Mapping, second: Mapping) -> dict:
    left, right = first.get("time_window") or {}, second.get("time_window") or {}
    starts = [x for x in (left.get("start"), right.get("start")) if isinstance(x, (int, float))]
    ends = [x for x in (left.get("end"), right.get("end")) if isinstance(x, (int, float))]
    strongest = right if _score(second) > _score(first) else left
    return {"start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
            "recommended_timestamp": strongest.get("recommended_timestamp"),
            "interval_is_observation_envelope": True}


def _score(row: Mapping) -> float:
    values = [row.get(key) for key in ("ratio_of_smaller", "overflow_x", "overflow_y")]
    return max((float(x) for x in values if isinstance(x, (int, float))), default=0.0)
