"""Primitive validation shared by immutable orchestration models."""

from manim_quality.contracts._formats import require_sha256


def require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def require_hash(value: object, name: str) -> None:
    require_sha256(value, name)
