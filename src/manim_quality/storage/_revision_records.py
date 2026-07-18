"""SQLite row encoding for immutable Revision contracts."""

from __future__ import annotations

import json
import sqlite3

from manim_quality.contracts import QualityState, Revision
from manim_quality.revisions.store import QualityJobSnapshot


def revision_payload(revision: Revision) -> str:
    return json.dumps(
        revision.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def revision_values(job_id: str, revision: Revision) -> tuple[object, ...]:
    return (
        revision.revision_id,
        job_id,
        revision.parent_revision_id,
        revision.stage.value,
        revision_payload(revision),
        revision.code_hash,
        revision.semantic_fingerprint,
        revision.render_manifest_hash,
    )


def revision_from_row(row: sqlite3.Row) -> Revision:
    return Revision.from_dict(json.loads(row["payload"]))


def row_matches(row: sqlite3.Row, job_id: str, revision: Revision) -> bool:
    return row["job_id"] == job_id and row["payload"] == revision_payload(revision)


def snapshot_from_row(row: sqlite3.Row) -> QualityJobSnapshot:
    return QualityJobSnapshot(
        job_id=row["job_id"],
        version=row["version"],
        state=QualityState(row["state"]),
        render_baseline_revision_id=row["render_baseline_revision_id"],
        logic_certified_revision_id=row["logic_certified_revision_id"],
        layout_certified_revision_id=row["layout_certified_revision_id"],
        delivery_revision_id=row["delivery_revision_id"],
        render_baseline_evidence_hash=row["render_baseline_evidence_hash"],
        logic_certified_evidence_hash=row["logic_certified_evidence_hash"],
        layout_certified_evidence_hash=row["layout_certified_evidence_hash"],
        delivery_evidence_hash=row["delivery_evidence_hash"],
    )
