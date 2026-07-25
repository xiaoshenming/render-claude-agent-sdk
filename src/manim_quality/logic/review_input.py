"""Versioned prompt input composition for the Logic Reviewer."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path

from manim_quality.geometry.schemas import GeometrySnapshot

from .evidence import LogicEvidence
from .review_digest import build_review_digest


class ReviewInputVersion(StrEnum):
    EVIDENCE_V1 = "evidence-v1"
    DIGEST_V2 = "digest-v2"
    DIGEST_V2_1 = "digest-v2-1"
    DIGEST_V2_2_GEOMETRY = "digest-v2-2-geometry"


_PROMPTS = {
    ReviewInputVersion.EVIDENCE_V1: Path(__file__).with_name("prompts") / "reviewer.md",
    ReviewInputVersion.DIGEST_V2: Path(__file__).with_name("prompts")
    / "reviewer_digest_v2.md",
    ReviewInputVersion.DIGEST_V2_1: Path(__file__).with_name("prompts")
    / "reviewer_digest_v2_1.md",
    ReviewInputVersion.DIGEST_V2_2_GEOMETRY: Path(__file__).with_name("prompts")
    / "reviewer_geometry_v1.md",
}


def build_review_prompt(
    *,
    evidence: LogicEvidence,
    candidate_code: str,
    candidate_path: Path,
    manifest_path: Path,
    input_version: ReviewInputVersion,
    geometry_snapshot: GeometrySnapshot | None = None,
) -> str:
    if not isinstance(input_version, ReviewInputVersion):
        raise TypeError("input_version must be ReviewInputVersion")
    body = (
        evidence.to_prompt_dict()
        if input_version is ReviewInputVersion.EVIDENCE_V1
        else build_review_digest(evidence, candidate_code).to_prompt_dict()
    )
    payload = _payload(
        candidate_path,
        manifest_path,
        input_version,
        body,
        geometry_snapshot,
    )
    compact = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    instructions = _PROMPTS[input_version].read_text(encoding="utf-8").strip()
    return f"{instructions}\n\nREVIEW_INPUT_JSON\n{compact}"


def _payload(
    candidate_path,
    manifest_path,
    input_version,
    body,
    geometry_snapshot,
):
    common = {
        "candidate_path": candidate_path.as_posix(),
        "render_manifest_path": manifest_path.as_posix(),
    }
    if input_version is ReviewInputVersion.EVIDENCE_V1:
        _reject_unused_geometry(geometry_snapshot)
        return {**common, "evidence": body}
    payload = {**common, "input_version": input_version.value, "digest": body}
    if input_version is ReviewInputVersion.DIGEST_V2_2_GEOMETRY:
        if not isinstance(geometry_snapshot, GeometrySnapshot):
            raise ValueError("geometry review input requires a geometry snapshot")
        payload["geometry_index"] = _geometry_index(geometry_snapshot)
    else:
        _reject_unused_geometry(geometry_snapshot)
    return payload


def _geometry_index(snapshot: GeometrySnapshot) -> dict[str, object]:
    if len(snapshot.objects) > 160:
        raise ValueError("geometry snapshot exceeds compact object catalog limit")
    return {
        "scene_id": snapshot.scene_id,
        "checkpoint_id": snapshot.checkpoint_id,
        "provenance": snapshot.provenance,
        "objects": [
            {
                "object_id": item.object_id,
                "kind": item.kind,
                "status": item.status.value,
                "reason_code": item.reason_code,
                "line_start": item.source.line_start,
            }
            for item in snapshot.objects
        ],
    }


def _reject_unused_geometry(snapshot: object) -> None:
    if snapshot is not None:
        raise ValueError("geometry snapshot requires geometry review input version")
