"""Normalization for bounded Reviewer metadata."""

from __future__ import annotations


def normalize_confidence(value: object, error_type: type[Exception]) -> float:
    if isinstance(value, bool):
        raise error_type("Reviewer confidence is invalid")
    if isinstance(value, str):
        qualitative = {"high": 0.9, "medium": 0.6, "low": 0.3}
        mapped = qualitative.get(value.strip().lower())
        if mapped is not None:
            return mapped
    percent = isinstance(value, str) and value.strip().endswith("%")
    if percent:
        value = value.strip()[:-1]
    try:
        confidence = float(value)
    except (TypeError, ValueError) as error:
        raise error_type("Reviewer confidence is invalid") from error
    if percent or 1 < confidence <= 100:
        confidence /= 100
    if not 0 <= confidence <= 1:
        raise error_type("Reviewer confidence must be between 0 and 1")
    return confidence
