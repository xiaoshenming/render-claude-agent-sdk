from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from .models import GRADES, AssuranceOutcome, Candidate

TTS_CATEGORIES = frozenset({"tts", "tts_sync", "audio", "narration", "subtitle_sync"})


def stable_issues(
    outcome: AssuranceOutcome,
    *,
    candidate: Candidate,
    assurance_pass: int,
    tts_mode: str,
) -> tuple[dict[str, object], ...]:
    rows = []
    for issue in outcome.issues:
        category = str(issue.get("category", "")).strip().lower()
        if tts_mode == "disabled" and category in TTS_CATEGORIES:
            continue
        row = dict(issue)
        row["issue_id"] = str(row.get("issue_id") or _issue_id(row))
        row["source_sha256"] = candidate.source_sha256
        row["video_sha256"] = candidate.video_sha256
        row["assurance_pass"] = assurance_pass
        rows.append(row)
    return tuple(rows)


def is_accepted(grade: str) -> bool:
    return grade in {"A", "B"}


def is_repairable(grade: str) -> bool:
    return grade in {"C", "D"}


def better_grade(current: str | None, proposed: str) -> bool:
    return current is None or GRADES.index(proposed) < GRADES.index(current)


def _issue_id(issue: Mapping[str, object]) -> str:
    evidence = issue.get("evidence_ids")
    normalized = {
        "category": issue.get("category"),
        "severity": issue.get("severity"),
        "summary": issue.get("summary"),
        "evidence_ids": sorted(evidence) if _sequence(evidence) else [],
    }
    encoded = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return f"fa-{hashlib.sha256(encoded).hexdigest()[:16]}"


def _sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))
