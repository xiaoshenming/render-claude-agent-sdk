"""Bounded state machine owned by one Quality Operator tool broker."""

from __future__ import annotations

from manim_quality.revisions.fingerprint import code_hash, sha256_text

from .models import (
    CandidateAttempt,
    Finding,
    PatchScope,
    ValidationRecord,
)
from .session_errors import (
    DuplicatePatch,
    InvalidSessionTransition,
    ScopeViolation,
)
from .session_rules import (
    embedded_problem_hash,
    patch_hash,
    validate_finding_scope,
    verify_candidate,
)
from .source_view import apply_solution_replacement, extract_solution


class QualitySession:
    """Own immutable inputs and at most five Agent-authored candidate attempts."""

    def __init__(
        self,
        *,
        problem_text: str,
        candidate_code: str,
        max_patch_attempts: int = 5,
    ) -> None:
        if not isinstance(problem_text, str) or not problem_text.strip():
            raise ValueError("problem_text must be non-empty")
        if not isinstance(candidate_code, str) or not candidate_code.strip():
            raise ValueError("candidate_code must be non-empty")
        if type(max_patch_attempts) is not int or max_patch_attempts <= 0:
            raise ValueError("max_patch_attempts must be positive")
        compile(candidate_code, "candidate.py", "exec")
        extract_solution(candidate_code)
        self._problem_text = problem_text
        self._problem_hash = sha256_text(problem_text)
        self._embedded_problem_hash = embedded_problem_hash(
            candidate_code,
            problem_text,
        )
        self._max_patch_attempts = max_patch_attempts
        self._attempts = [
            CandidateAttempt(
                revision_id="R0",
                parent_revision_id=None,
                scope=None,
                code=candidate_code,
                code_hash=code_hash(candidate_code),
                patch_hash=None,
                finding_ids=(),
            )
        ]
        self._findings: dict[str, Finding] = {}
        self._finding_batches = 0
        self._validations: dict[str, ValidationRecord] = {}
        self._layout_inspections: dict[str, tuple[str, int]] = {}
        self._seen_code_hashes = {self._attempts[0].code_hash}
        self._submitted_revision_id: str | None = None
        self._solution_reads: set[str] = set()

    @property
    def problem_text(self) -> str:
        return self._problem_text

    @property
    def problem_hash(self) -> str:
        return self._problem_hash

    @property
    def baseline(self) -> CandidateAttempt:
        return self._attempts[0]

    @property
    def current_revision(self) -> CandidateAttempt:
        return self._attempts[-1]

    @property
    def attempts(self) -> tuple[CandidateAttempt, ...]:
        return tuple(self._attempts)

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings.values())

    @property
    def submitted_revision_id(self) -> str | None:
        return self._submitted_revision_id

    def get_revision(self, revision_id: str) -> CandidateAttempt:
        for attempt in self._attempts:
            if attempt.revision_id == revision_id:
                return attempt
        raise ValueError(f"unknown revision_id: {revision_id}")

    def mark_solution_read(self, revision_id: str) -> None:
        self._require_open()
        self.get_revision(revision_id)
        self._solution_reads.add(revision_id)

    def record_findings(self, findings: tuple[Finding, ...]) -> None:
        self._require_open()
        if not isinstance(findings, tuple):
            raise TypeError("findings must be a tuple")
        if self.current_revision.revision_id not in self._solution_reads:
            raise InvalidSessionTransition(
                "read_solution must cover the current revision before findings"
            )
        if self._finding_batches >= 3:
            raise InvalidSessionTransition("finding batch budget exhausted")
        if (
            self.current_revision.revision_id != "R0"
            and self.current_revision.revision_id not in self._validations
        ):
            raise InvalidSessionTransition(
                "current revision must be validated before new findings"
            )
        values: dict[str, Finding] = {}
        for item in findings:
            if not isinstance(item, Finding):
                raise TypeError("findings must contain Finding values")
            if item.finding_id in values or item.finding_id in self._findings:
                raise ValueError(f"duplicate finding_id: {item.finding_id}")
            values[item.finding_id] = item
        self._findings.update(values)
        self._finding_batches += 1

    def apply_patch(
        self,
        *,
        scope: PatchScope,
        old_text: str,
        new_text: str,
        finding_ids: tuple[str, ...],
    ) -> CandidateAttempt:
        self._require_patch_allowed(scope, finding_ids)
        before = self.current_revision
        if before.revision_id not in self._solution_reads:
            raise InvalidSessionTransition(
                "read_solution must cover the current revision before patch"
            )
        if old_text == new_text:
            raise ValueError("patch must change content")
        if len(old_text) > 200 and len(new_text) * 2 < len(old_text):
            raise ScopeViolation("patch removes too much content in one block")
        after_code = apply_solution_replacement(
            before.code,
            old_text=old_text,
            new_text=new_text,
        )
        verify_candidate(
            problem_text=self._problem_text,
            baseline=self.baseline,
            current=self.current_revision,
            embedded_hash=self._embedded_problem_hash,
            code=after_code,
            scope=scope,
        )
        after_hash = code_hash(after_code)
        if after_hash in self._seen_code_hashes:
            raise DuplicatePatch("patch recreates an already seen candidate")
        attempt = CandidateAttempt(
            revision_id=f"R{len(self._attempts)}",
            parent_revision_id=before.revision_id,
            scope=scope,
            code=after_code,
            code_hash=after_hash,
            patch_hash=patch_hash(before.code, after_code),
            finding_ids=finding_ids,
        )
        self._attempts.append(attempt)
        self._solution_reads.add(attempt.revision_id)
        self._seen_code_hashes.add(after_hash)
        return attempt

    def record_validation(
        self,
        *,
        revision_id: str,
        passed: bool,
        improved: bool,
        fingerprint: str,
    ) -> ValidationRecord:
        self._require_open()
        if revision_id != self.current_revision.revision_id or revision_id == "R0":
            raise InvalidSessionTransition(
                "only the current candidate can be validated"
            )
        if revision_id in self._validations:
            raise InvalidSessionTransition("candidate was already validated")
        record = ValidationRecord(revision_id, passed, improved, fingerprint)
        self._validations[revision_id] = record
        return record

    def record_layout_inspection(
        self,
        *,
        revision_id: str,
        fingerprint: str,
        blocking_count: int = 0,
    ) -> None:
        self._require_open()
        if revision_id != self.current_revision.revision_id:
            raise InvalidSessionTransition(
                "only the current revision can bind layout inspection"
            )
        if (
            not isinstance(fingerprint, str)
            or not fingerprint.startswith("sha256:")
            or len(fingerprint) != 71
        ):
            raise ValueError("fingerprint must be a sha256 digest")
        if (
            isinstance(blocking_count, bool)
            or not isinstance(blocking_count, int)
            or blocking_count < 0
        ):
            raise ValueError("blocking_count must be a non-negative integer")
        self._layout_inspections[revision_id] = (fingerprint, blocking_count)

    def submit(self, revision_id: str) -> CandidateAttempt:
        self._require_open()
        current = self.current_revision
        if revision_id != current.revision_id:
            raise InvalidSessionTransition("only the current revision can be submitted")
        if revision_id != "R0" and revision_id not in self._validations:
            raise InvalidSessionTransition("latest revision must be validated")
        if (
            revision_id != "R0"
            and not self._validations[revision_id].passed
        ):
            raise InvalidSessionTransition(
                "latest revision must pass validation before submit"
            )
        if self._finding_batches == 0:
            raise InvalidSessionTransition("findings must be recorded before submit")
        blocking = {
            item.finding_id
            for item in self._findings.values()
            if item.severity == "blocking"
        }
        repaired = {
            finding_id
            for attempt in self._attempts[1:]
            for finding_id in attempt.finding_ids
        }
        if not blocking.issubset(repaired):
            raise InvalidSessionTransition(
                "blocking findings require a validated repair revision"
            )
        if revision_id not in self._layout_inspections:
            raise InvalidSessionTransition(
                "current revision requires a fresh layout inspection"
            )
        if self._layout_inspections[revision_id][1] > 0:
            raise InvalidSessionTransition(
                "current revision still has blocking layout issues"
            )
        self._submitted_revision_id = revision_id
        return current

    def _require_patch_allowed(
        self, scope: PatchScope, finding_ids: tuple[str, ...]
    ) -> None:
        self._require_open()
        if not isinstance(scope, PatchScope):
            raise TypeError("scope must be a PatchScope")
        if self._finding_batches == 0:
            raise InvalidSessionTransition("findings must be recorded before patch")
        if len(self._attempts) - 1 >= self._max_patch_attempts:
            raise InvalidSessionTransition("patch attempt budget exhausted")
        if any(item.scope is PatchScope.LAYOUT for item in self._attempts):
            if scope is PatchScope.LOGIC:
                raise InvalidSessionTransition("logic patch is forbidden after layout")
        current_validation = self._validations.get(self.current_revision.revision_id)
        if self.current_revision.revision_id != "R0":
            if current_validation is None:
                raise InvalidSessionTransition("current revision must be validated")
            if not current_validation.improved:
                raise InvalidSessionTransition("previous revision did not improve")
        validate_finding_scope(self._findings, scope, finding_ids)

    def _require_open(self) -> None:
        if self._submitted_revision_id is not None:
            raise InvalidSessionTransition("session was already submitted")
