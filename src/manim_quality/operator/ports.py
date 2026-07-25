"""Injected deterministic services used by Quality Operator tools."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from .models import CandidateAttempt, Finding, ValidationOutcome


class RelationChecker(Protocol):
    async def check(
        self, request: Mapping[str, object]
    ) -> Mapping[str, object]: ...


class LayoutInspector(Protocol):
    async def inspect(
        self,
        revision: CandidateAttempt,
        problem_hash: str,
    ) -> Mapping[str, object]: ...


class RevisionValidator(Protocol):
    async def validate(
        self,
        revision: CandidateAttempt,
        findings: tuple[Finding, ...],
        problem_hash: str,
    ) -> ValidationOutcome: ...
