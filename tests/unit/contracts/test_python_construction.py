from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

import pytest

from manim_quality.contracts import (
    DeliveryDecision,
    PatchScope,
    QualityResult,
    QualitySubmission,
    Revision,
    RevisionCreator,
    RevisionStage,
)

HASH_A = f"sha256:{'a' * 64}"
HASH_B = f"sha256:{'b' * 64}"


def test_replace_reuses_submission_frozen_planning() -> None:
    submission = QualitySubmission(
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
    )

    replaced = replace(submission, problem_text="Find y.")

    assert replaced.planning == submission.planning
    assert replaced.to_dict()["planning"] == {"scenes": [{"id": "SceneA"}]}


def test_replace_reuses_revision_frozen_scene_evidence_without_reordering() -> None:
    revision = Revision(
        revision_id="rev-1",
        parent_revision_id=None,
        stage=RevisionStage.BASELINE,
        code_hash=HASH_A,
        semantic_fingerprint=HASH_B,
        scene_hashes={"SceneB": HASH_B, "SceneA": HASH_A},
        render_manifest_hash=None,
        changed_scene_ids=["SceneB", "SceneA"],
        patch_scope=PatchScope.FULL_CANDIDATE,
        created_by=RevisionCreator.SYSTEM,
        attempt=0,
    )

    replaced = replace(revision, attempt=1)

    assert replaced.scene_hashes == revision.scene_hashes
    assert replaced.changed_scene_ids is revision.changed_scene_ids
    assert replaced.changed_scene_ids == ("SceneB", "SceneA")


def test_replace_reuses_result_frozen_collections() -> None:
    result = QualityResult(
        job_id="job-1",
        decision=DeliveryDecision.ACCEPT,
        accepted_revision_id="rev-1",
        final_code_ref="artifact://final.py",
        final_render_manifest_ref="artifact://render.json",
        certificate_ref="artifact://certificate.json",
        warnings=[],
        token_usage={"reviewer": 10},
        timings_ms={"reviewer": 20},
    )

    replaced = replace(result, certificate_ref="artifact://certificate-2.json")

    assert replaced.warnings is result.warnings
    assert replaced.token_usage == result.token_usage
    assert replaced.timings_ms == result.timings_ms


def test_direct_construction_detaches_external_mappingproxy_backing_dicts() -> None:
    planning_source: dict[str, object] = {"scene": "SceneA"}
    scene_hash_source = {"SceneA": HASH_A}
    usage_source = {"reviewer": 10}

    submission = QualitySubmission(
        job_id="job-1",
        tenant_id="tenant-1",
        candidate_code_ref="artifact://candidate.py",
        problem_text="Find x.",
        planning=MappingProxyType(planning_source),
        expected_answer=None,
        render_manifest_ref=None,
        asset_manifest_ref=None,
        callback_url=None,
        idempotency_key="quality:job-1:1",
    )
    revision = Revision(
        revision_id="rev-1",
        parent_revision_id=None,
        stage=RevisionStage.BASELINE,
        code_hash=HASH_A,
        semantic_fingerprint=HASH_B,
        scene_hashes=MappingProxyType(scene_hash_source),
        render_manifest_hash=None,
        changed_scene_ids=("SceneA",),
        patch_scope=PatchScope.FULL_CANDIDATE,
        created_by=RevisionCreator.SYSTEM,
        attempt=0,
    )
    result = QualityResult(
        job_id="job-1",
        decision=DeliveryDecision.ACCEPT,
        accepted_revision_id="rev-1",
        final_code_ref="artifact://final.py",
        final_render_manifest_ref="artifact://render.json",
        certificate_ref="artifact://certificate.json",
        warnings=(),
        token_usage=MappingProxyType(usage_source),
        timings_ms=MappingProxyType({"reviewer": 20}),
    )

    planning_source["scene"] = "mutated"
    scene_hash_source["SceneA"] = HASH_B
    usage_source["reviewer"] = 999

    assert submission.to_dict()["planning"] == {"scene": "SceneA"}
    assert revision.to_dict()["scene_hashes"] == {"SceneA": HASH_A}
    assert result.to_dict()["token_usage"] == {"reviewer": 10}


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [("scene_hashes", []), ("changed_scene_ids", object())],
)
def test_direct_revision_construction_rejects_invalid_python_containers(
    field_name: str,
    invalid_value: object,
) -> None:
    revision = Revision(
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
    )

    with pytest.raises(TypeError, match=field_name):
        replace(revision, **{field_name: invalid_value})


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [("warnings", object()), ("token_usage", [])],
)
def test_direct_result_construction_rejects_invalid_python_containers(
    field_name: str,
    invalid_value: object,
) -> None:
    result = QualityResult(
        job_id="job-1",
        decision=DeliveryDecision.ACCEPT,
        accepted_revision_id="rev-1",
        final_code_ref="artifact://final.py",
        final_render_manifest_ref="artifact://render.json",
        certificate_ref="artifact://certificate.json",
        warnings=[],
        token_usage={},
        timings_ms={},
    )

    with pytest.raises(TypeError, match=field_name):
        replace(result, **{field_name: invalid_value})
