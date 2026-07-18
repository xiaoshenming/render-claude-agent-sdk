"""Canonical, URI-independent evidence serialization."""

import json

from manim_quality.revisions.fingerprint import sha256_bytes


def canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def content_hash(payload: object) -> str:
    return sha256_bytes(canonical_bytes(payload))
