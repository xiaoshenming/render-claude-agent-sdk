from __future__ import annotations

from collections.abc import Callable

from manim_quality.contracts import (
    DeliveryDecision,
    PatchScope,
    QualityResult,
    QualitySubmission,
    Revision,
    RevisionCreator,
    RevisionStage,
)

PayloadFactory = Callable[[], dict[str, object]]
Deserializer = Callable[[object], object]
HASH_A = f"sha256:{'a' * 64}"
HASH_B = f"sha256:{'b' * 64}"


def submission_payload() -> dict[str, object]:
    return QualitySubmission(
        job_id="job-1",
        tenant_id="tenant-1",
        candidate_code_ref="artifact://candidate.py",
        problem_text="Find x.",
        planning={"scenes": [{"id": "SceneA"}]},
        expected_answer=None,
        render_manifest_ref=None,
        asset_manifest_ref=None,
        callback_url=None,
        idempotency_key="quality:job-1:1",
    ).to_dict()


def revision_payload() -> dict[str, object]:
    return Revision(
        revision_id="rev-1",
        parent_revision_id=None,
        stage=RevisionStage.BASELINE,
        code_hash=HASH_A,
        semantic_fingerprint=HASH_B,
        scene_hashes={"SceneA": HASH_A},
        render_manifest_hash=None,
        changed_scene_ids=["SceneA"],
        patch_scope=PatchScope.FULL_CANDIDATE,
        created_by=RevisionCreator.SYSTEM,
        attempt=0,
    ).to_dict()


def result_payload() -> dict[str, object]:
    return QualityResult(
        job_id="job-1",
        decision=DeliveryDecision.ACCEPT,
        accepted_revision_id="rev-1",
        final_code_ref="artifact://final.py",
        final_render_manifest_ref="artifact://render.json",
        certificate_ref="artifact://certificate.json",
        warnings=[],
        token_usage={"reviewer": 10},
        timings_ms={"reviewer": 20},
    ).to_dict()


CONTRACT_CASES = (
    ("submission", QualitySubmission.from_dict, submission_payload),
    ("revision", Revision.from_dict, revision_payload),
    ("result", QualityResult.from_dict, result_payload),
)
