from __future__ import annotations
from collections.abc import Mapping
from manim_quality.revisions.fingerprint import code_hash
from .finding_dependencies import validate_finding_dependencies
from .immutable_inputs import ImmutableReviewInputs
from .models import (
    CandidateAttempt,
    Finding,
    PatchScope,
    ValidationRecord,
)
from .session_errors import (
    DuplicatePatch,
    InvalidSessionTransition,
)
from .session_rules import (
    best_validated_revision,
    embedded_problem_hash,
    patch_hash,
    validate_layout_inspection,
    validate_patch_budget_raise,
    validate_patch_text,
    validate_recovery_revision,
    validate_session_patch,
    verify_candidate,
)
from .source_view import apply_solution_replacement, extract_solution
class QualitySession:
    """Own immutable inputs and a configured number of candidate attempts."""

    def __init__(
        self,
        *,
        problem_text: str,
        candidate_code: str,
        solution_steps: str = "",
        parsed_standard_answer: str = "",
        reviewer_supplemental_notes: Mapping[str, object] | None = None,
        repair_feedback: Mapping[str, object] | None = None,
        max_patch_attempts: int = 12,
    ) -> None:
        if not isinstance(problem_text, str) or not problem_text.strip():
            raise ValueError("problem_text must be non-empty")
        if not isinstance(candidate_code, str) or not candidate_code.strip():
            raise ValueError("candidate_code must be non-empty")
        if type(max_patch_attempts) is not int or max_patch_attempts <= 0:
            raise ValueError("max_patch_attempts must be positive")
        compile(candidate_code, "candidate.py", "exec")
        extract_solution(candidate_code)
        self._review_inputs = ImmutableReviewInputs.build(
            problem_text, solution_steps, parsed_standard_answer,
            reviewer_supplemental_notes, repair_feedback,
        )
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
        self._active_revision_id = "R0"
        self._findings: dict[str, Finding] = {}
        self._finding_batches = 0
        self._validations: dict[str, ValidationRecord] = {}
        self._layout_inspections: dict[str, tuple[str, int]] = {}
        self._seen_code_hashes = {self._attempts[0].code_hash}
        self._submitted_revision_id: str | None = None
        self._solution_reads: set[str] = set()

    problem_text = property(lambda self: self._review_inputs.problem_text)
    problem_hash = property(lambda self: self._review_inputs.problem_hash)
    parsed_standard_answer = property(
        lambda self: self._review_inputs.parsed_standard_answer)
    solution_steps = property(lambda self: self._review_inputs.solution_steps)
    reviewer_supplemental_notes = property(
        lambda self: dict(self._review_inputs.reviewer_supplemental_notes))
    solution_steps_hash = property(
        lambda self: self._review_inputs.solution_steps_hash
    )
    repair_feedback = property(
        lambda self: dict(self._review_inputs.repair_feedback)
    )
    repair_feedback_hash = property(
        lambda self: self._review_inputs.repair_feedback_hash
    )

    @property
    def baseline(self) -> CandidateAttempt:
        return self._attempts[0]
    @property
    def current_revision(self) -> CandidateAttempt:
        return self.get_revision(self._active_revision_id)
    @property
    def attempts(self) -> tuple[CandidateAttempt, ...]:
        return tuple(self._attempts)

    @property
    def findings(self) -> tuple[Finding, ...]:
        return tuple(self._findings.values())

    @property
    def submitted_revision_id(self) -> str | None:
        return self._submitted_revision_id

    @property
    def max_patch_attempts(self) -> int:
        return self._max_patch_attempts

    @property
    def patches_remaining(self) -> int:
        return self._max_patch_attempts - (len(self._attempts) - 1)

    @property
    def finding_batches_remaining(self) -> int:
        return 12 - self._finding_batches

    def raise_patch_budget(self, max_patch_attempts: int) -> None:
        self._require_open()
        validate_patch_budget_raise(self._max_patch_attempts, max_patch_attempts)
        if self._finding_batches > 0 or len(self._attempts) > 1:
            raise InvalidSessionTransition(
                "patch budget is frozen after findings or patches"
            )
        self._max_patch_attempts = max_patch_attempts

    def get_revision(self, revision_id: str) -> CandidateAttempt:
        for attempt in self._attempts:
            if attempt.revision_id == revision_id:
                return attempt
        raise ValueError(f"unknown revision_id: {revision_id}")

    def best_validated_evidence(self) -> dict[str, object] | None:
        return best_validated_revision(
            self._attempts,
            self._validations,
            self._layout_inspections,
        )

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
        if self._finding_batches >= 12:
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
        validate_finding_dependencies(self._findings, values)
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
        self._require_open()
        validate_session_patch(self, scope, finding_ids)
        before = self.current_revision
        if before.revision_id not in self._solution_reads:
            raise InvalidSessionTransition(
                "read_solution must cover the current revision before patch"
            )
        validate_patch_text(old_text, new_text)
        after_code = apply_solution_replacement(
            before.code,
            old_text=old_text,
            new_text=new_text,
        )
        verify_candidate(
            problem_text=self.problem_text,
            baseline=self.baseline,
            embedded_hash=self._embedded_problem_hash,
            code=after_code,
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
        self._active_revision_id = attempt.revision_id
        self._solution_reads.add(attempt.revision_id)
        self._seen_code_hashes.add(after_hash)
        return attempt

    def recover_revision(self, revision_id: str) -> CandidateAttempt:
        self._require_open()
        target = self.get_revision(revision_id)
        validate_recovery_revision(
            target, self.current_revision, self._validations
        )
        self._active_revision_id = target.revision_id
        self._solution_reads.discard(target.revision_id)
        return target

    def record_validation(
        self,
        *,
        revision_id: str,
        passed: bool,
        improved: bool,
        fingerprint: str,
    ) -> ValidationRecord:
        self._require_open()
        if revision_id != self.current_revision.revision_id:
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
        validate_layout_inspection(fingerprint, blocking_count)
        self._layout_inspections[revision_id] = (fingerprint, blocking_count)

    def submit(self, revision_id: str) -> CandidateAttempt:
        self._require_open()
        current = self.current_revision
        if revision_id != current.revision_id:
            raise InvalidSessionTransition("only the current revision can be submitted")
        self._validate_submission(revision_id)
        self._submitted_revision_id = revision_id
        return current

    def _validate_submission(self, revision_id: str) -> None:
        if revision_id != "R0" and revision_id not in self._validations:
            raise InvalidSessionTransition("latest revision must be validated")
        if revision_id != "R0" and not self._validations[revision_id].passed:
            raise InvalidSessionTransition(
                "latest revision must pass validation before submit"
            )
        if self._finding_batches == 0:
            raise InvalidSessionTransition("findings must be recorded before submit")
        if revision_id not in self._layout_inspections:
            raise InvalidSessionTransition(
                "current revision requires a fresh layout inspection"
            )
        if self._layout_inspections[revision_id][1] > 0:
            raise InvalidSessionTransition(
                "current revision still has blocking layout issues"
            )

    def _require_open(self) -> None:
        if self._submitted_revision_id is not None:
            raise InvalidSessionTransition("session was already submitted")
