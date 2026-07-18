"""MathPi adapter for the vendored Manim quality platform."""

from .pre_archive import (
    PreArchiveQualityRequest,
    PreArchiveQualityResult,
    run_pre_archive_quality_platform,
)

__all__ = [
    "PreArchiveQualityRequest",
    "PreArchiveQualityResult",
    "run_pre_archive_quality_platform",
]
