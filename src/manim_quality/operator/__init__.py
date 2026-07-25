"""Unified Quality Agent MVP domain."""

from .models import CandidateAttempt, Finding, FindingCategory, PatchScope
from .session import QualitySession
from .source_view import (
    SolutionSource,
    SolutionSourceError,
    apply_solution_replacement,
    extract_solution,
)

__all__ = [
    "CandidateAttempt",
    "Finding",
    "FindingCategory",
    "PatchScope",
    "QualitySession",
    "SolutionSource",
    "SolutionSourceError",
    "apply_solution_replacement",
    "extract_solution",
]
