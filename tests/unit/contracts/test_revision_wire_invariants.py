from __future__ import annotations

import pytest
from contract_samples import revision_payload

from manim_quality.contracts import Revision

HASH_A = f"sha256:{'a' * 64}"
HASH_B = f"sha256:{'b' * 64}"


def _valid_payload() -> dict[str, object]:
    payload = revision_payload()
    payload["code_hash"] = HASH_A
    payload["semantic_fingerprint"] = HASH_B
    payload["scene_hashes"] = {"SceneA": HASH_A, "SceneB": HASH_B}
    payload["render_manifest_hash"] = HASH_A
    return payload


def test_changed_scene_ids_preserve_original_wire_order_roundtrip() -> None:
    payload = _valid_payload()
    payload["changed_scene_ids"] = ["SceneB", "SceneA"]

    restored = Revision.from_dict(payload)

    assert restored.changed_scene_ids == ("SceneB", "SceneA")
    assert restored.to_dict()["changed_scene_ids"] == ["SceneB", "SceneA"]


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("code_hash", 42),
        ("code_hash", f"sha256:{'A' * 64}"),
        ("semantic_fingerprint", f"sha256:{'a' * 63}"),
        ("render_manifest_hash", f"sha512:{'a' * 64}"),
        ("scene_hashes", {"SceneA": f"sha256:{'g' * 64}"}),
    ],
)
def test_revision_rejects_noncanonical_sha256_hashes(
    field_name: str,
    invalid_value: object,
) -> None:
    payload = _valid_payload()
    payload[field_name] = invalid_value

    with pytest.raises((TypeError, ValueError), match=field_name):
        Revision.from_dict(payload)


def test_revision_accepts_canonical_sha256_hashes() -> None:
    payload = _valid_payload()

    assert Revision.from_dict(payload).to_dict() == payload
