from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, is_dataclass

import pytest

from manim_quality.contracts import (
    PatchScope,
    Revision,
    RevisionCreator,
    RevisionStage,
)

HASH_A = f"sha256:{'a' * 64}"
HASH_B = f"sha256:{'b' * 64}"
HASH_C = f"sha256:{'c' * 64}"


def _revision() -> Revision:
    return Revision(
        revision_id="rev-002",
        parent_revision_id="rev-001",
        stage=RevisionStage.LOGIC_REPAIR,
        code_hash=HASH_A,
        semantic_fingerprint=HASH_B,
        scene_hashes={"SceneB": HASH_B, "SceneA": HASH_A},
        render_manifest_hash=HASH_C,
        changed_scene_ids=["SceneB", "SceneA"],
        patch_scope=PatchScope.SCENE_LOGIC,
        created_by=RevisionCreator.LOGIC_AGENT,
        attempt=1,
    )


def test_revision_is_frozen_slotted_and_roundtrips_stably() -> None:
    revision = _revision()

    assert is_dataclass(revision)
    assert revision.__dataclass_params__.frozen is True
    assert not hasattr(revision, "__dict__")
    assert "schema_version" in {item.name for item in fields(revision)}
    with pytest.raises(FrozenInstanceError):
        revision.attempt = 2  # type: ignore[misc]

    payload = revision.to_dict()
    restored = Revision.from_dict(payload)

    assert restored == revision
    assert list(payload["scene_hashes"]) == ["SceneA", "SceneB"]
    assert payload["stage"] == "LOGIC_REPAIR"
    assert payload["patch_scope"] == "scene_logic"
    assert payload["created_by"] == "logic_agent"
    assert json.dumps(restored.to_dict(), separators=(",", ":")) == json.dumps(
        payload, separators=(",", ":")
    )


def test_revision_deep_freezes_scene_evidence() -> None:
    scene_hashes = {"SceneA": HASH_A}
    changed_scene_ids = ["SceneA"]
    revision = Revision(
        revision_id="rev-001",
        parent_revision_id=None,
        stage=RevisionStage.BASELINE,
        code_hash=HASH_A,
        semantic_fingerprint=HASH_B,
        scene_hashes=scene_hashes,
        render_manifest_hash=None,
        changed_scene_ids=changed_scene_ids,
        patch_scope=PatchScope.FULL_CANDIDATE,
        created_by=RevisionCreator.SYSTEM,
        attempt=0,
    )

    scene_hashes["SceneA"] = HASH_C
    changed_scene_ids.append("SceneB")

    assert revision.to_dict()["scene_hashes"] == {"SceneA": HASH_A}
    assert revision.changed_scene_ids == ("SceneA",)
    with pytest.raises(TypeError):
        revision.scene_hashes["SceneB"] = HASH_B  # type: ignore[index]


@pytest.mark.parametrize(
    ("field_name", "value", "match"),
    [
        ("schema_version", "unsupported", "schema_version"),
        ("stage", "UNKNOWN", "stage"),
        ("patch_scope", "unknown", "patch_scope"),
        ("created_by", "unknown", "created_by"),
    ],
)
def test_revision_from_dict_rejects_schema_and_enum_values(
    field_name: str,
    value: object,
    match: str,
) -> None:
    payload = _revision().to_dict()
    payload[field_name] = value

    with pytest.raises(ValueError, match=match):
        Revision.from_dict(payload)


@pytest.mark.parametrize("mutation", ["missing_schema", "unknown_field"])
def test_revision_from_dict_rejects_invalid_contract_shape(mutation: str) -> None:
    payload = _revision().to_dict()
    if mutation == "missing_schema":
        payload.pop("schema_version")
    else:
        payload["extra"] = True

    with pytest.raises((TypeError, ValueError), match="schema_version|unknown field"):
        Revision.from_dict(payload)


@pytest.mark.parametrize(
    "field_name",
    ["revision_id", "code_hash", "semantic_fingerprint", "render_manifest_hash"],
)
def test_revision_rejects_blank_identifiers_and_hashes(field_name: str) -> None:
    payload = _revision().to_dict()
    payload[field_name] = " "

    with pytest.raises(ValueError, match=field_name):
        Revision.from_dict(payload)


def test_revision_rejects_invalid_scene_evidence_and_attempt() -> None:
    payload = _revision().to_dict()
    payload["scene_hashes"] = {"": HASH_A}
    with pytest.raises(ValueError, match="scene_hashes"):
        Revision.from_dict(payload)

    payload = _revision().to_dict()
    payload["changed_scene_ids"] = [""]
    with pytest.raises(ValueError, match="changed_scene_ids"):
        Revision.from_dict(payload)

    payload = _revision().to_dict()
    payload["attempt"] = -1
    with pytest.raises(ValueError, match="attempt"):
        Revision.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("scene_hashes", []),
        ("changed_scene_ids", "SceneA"),
        ("changed_scene_ids", ["SceneA", "SceneA"]),
        ("attempt", True),
        ("stage", 1),
    ],
)
def test_revision_rejects_wrong_container_and_scalar_types(
    field_name: str,
    value: object,
) -> None:
    payload = _revision().to_dict()
    payload[field_name] = value

    with pytest.raises((TypeError, ValueError), match=field_name):
        Revision.from_dict(payload)
