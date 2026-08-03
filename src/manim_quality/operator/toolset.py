"""Evidence and validation tools used alongside native Read/Edit."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock

from manim_quality.agents.managed_tools import ManagedToolGrant
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.revisions.fingerprint import sha256_text

from .models import FindingCategory, PatchScope, ValidationOutcome
from .ports import LayoutInspector, RelationChecker, RevisionValidator
from .session import QualitySession
from .source_view import extract_solution
from .tool_contracts import (
    bind_findings,
    bind_relation,
    bind_revision_id,
)
from .tool_registry import register_quality_tools


def build_quality_tools(
    *,
    session: QualitySession,
    relation_checker: RelationChecker,
    layout_inspector: LayoutInspector,
    revision_validator: RevisionValidator,
    candidate_path: Path | None = None,
) -> tuple[ManagedToolGrant, ...]:
    handlers = _Handlers(
        session,
        relation_checker,
        layout_inspector,
        revision_validator,
        candidate_path,
    )
    return register_quality_tools(handlers)


class _Handlers:
    def __init__(self, session, relation, layout, validator, candidate_path) -> None:
        self.session = session
        self.relation = relation
        self.layout = layout
        self.validator = validator
        self.candidate_path = (
            Path(candidate_path).resolve(strict=True)
            if candidate_path is not None
            else None
        )
        # Managed tools may execute in different event-loop threads.  An
        # anyio.Lock only serializes tasks in one loop and allowed two
        # validators to create the same immutable revision concurrently.
        self._sync_lock = Lock()

    async def check_relation(self, arguments):
        return _json_text(await self.relation.check(bind_relation(arguments)))

    async def record_findings(self, arguments):
        findings = bind_findings(arguments)
        self.session.record_findings(findings)
        return _json_text(
            {
                "status": "recorded",
                "finding_count": len(findings),
                "finding_ids": [item.finding_id for item in findings],
            }
        )

    async def recover_revision(self, arguments):
        revision_id = bind_revision_id(arguments)
        if revision_id == "best_render_passed":
            evidence = self.session.best_validated_evidence()
            revision_id = (
                str(evidence["revision_id"]) if evidence is not None else "R0"
            )
        revision = self.session.recover_revision(revision_id)
        if self.candidate_path is not None:
            self.candidate_path.write_text(revision.code, encoding="utf-8")
        return _json_text(
            {
                "status": "recovered",
                "revision_id": revision.revision_id,
                "code_hash": revision.code_hash,
                **_budget_signal(self.session),
            }
        )

    async def inspect_layout(self, arguments):
        revision = await self._sync_native_candidate(
            _bind_finding_ids(arguments)
        )
        report = await self.layout.inspect(
            revision,
            self.session.problem_hash,
        )
        identity = (
            report.get("revision_id"),
            report.get("code_hash"),
            report.get("problem_hash"),
        )
        expected = (
            revision.revision_id,
            revision.code_hash,
            self.session.problem_hash,
        )
        if identity != expected:
            raise ValueError("layout inspector returned stale evidence")
        report = {**report, **_budget_signal(self.session)}
        text = _json_text(report)
        blocking = report.get("blocking_count")
        if type(blocking) is not int or blocking < 0:
            raise ValueError("layout report has invalid blocking_count")
        self.session.record_layout_inspection(
            revision_id=revision.revision_id,
            fingerprint=sha256_text(text),
            blocking_count=blocking,
        )
        return text

    async def validate_revision(self, arguments):
        revision = await self._sync_native_candidate(
            _bind_finding_ids(arguments)
        )
        outcome = await self.validator.validate(
            revision,
            self.session.findings,
            self.session.problem_hash,
        )
        if not isinstance(outcome, ValidationOutcome):
            raise TypeError("revision validator returned malformed outcome")
        expected = (
            revision.revision_id,
            revision.code_hash,
            self.session.problem_hash,
        )
        actual = (outcome.revision_id, outcome.code_hash, outcome.problem_hash)
        if actual != expected:
            raise ValueError("revision validator returned stale evidence")
        self.session.record_validation(
            revision_id=revision.revision_id,
            passed=outcome.passed,
            improved=outcome.improved,
            fingerprint=outcome.fingerprint,
        )
        receipt = _validation_receipt(revision.revision_id, outcome)
        return _json_text({**receipt, **_budget_signal(self.session)})

    async def submit_revision(self, arguments):
        del arguments
        current = self.session.current_revision
        if (
            self.candidate_path is not None
            and self.candidate_path.read_text(encoding="utf-8") != current.code
        ):
            raise ValueError("native Edit must be validated before submission")
        revision = self.session.submit(current.revision_id)
        return _json_text(
            {
                "status": "submitted",
                "submitted_revision_id": revision.revision_id,
                "code_hash": revision.code_hash,
                "problem_hash": self.session.problem_hash,
            }
        )

    async def _sync_native_candidate(self, finding_ids=()):
        with self._sync_lock:
            current = self.session.current_revision
            if self.candidate_path is None:
                return current
            edited = self.candidate_path.read_text(encoding="utf-8")
            if edited == current.code:
                _require_current_binding(current, finding_ids)
                return current
            before = extract_solution(current.code)
            after = extract_solution(edited)
            scope = _native_edit_scope(self.session, finding_ids)
            return self.session.apply_patch(
                scope=scope,
                old_text=before.source,
                new_text=after.source,
                finding_ids=finding_ids,
            )


def _bind_finding_ids(arguments) -> tuple[str, ...]:
    values = arguments.get("finding_ids", ())
    if not isinstance(values, (list, tuple)) or len(values) > 12:
        raise ValueError("finding_ids must be an array of at most 12 items")
    finding_ids = tuple(values)
    if any(not isinstance(item, str) or not item.strip() for item in finding_ids):
        raise ValueError("finding_ids must contain non-empty strings")
    if len(set(finding_ids)) != len(finding_ids):
        raise ValueError("finding_ids must not contain duplicates")
    return finding_ids


def _native_edit_scope(session, finding_ids: tuple[str, ...]) -> PatchScope:
    if not finding_ids:
        return PatchScope.LOGIC
    findings = {item.finding_id: item for item in session.findings}
    unknown = set(finding_ids) - set(findings)
    if unknown:
        raise ValueError(f"unknown finding_ids: {sorted(unknown)}")
    categories = {findings[item].category for item in finding_ids}
    # A native Edit can accumulate several independently authored changes
    # before the next managed validation call. Treat that combined revision as
    # logic-capable when any bound finding is logical, while preserving all
    # finding IDs in the revision ledger.
    return (
        PatchScope.LOGIC
        if FindingCategory.LOGIC in categories
        else PatchScope.LAYOUT
    )


def _require_current_binding(current, finding_ids: tuple[str, ...]) -> None:
    if current.revision_id == "R0":
        if finding_ids:
            raise ValueError("R0 validation must use empty finding_ids")
        return
    if finding_ids != current.finding_ids:
        raise ValueError(
            "finding_ids must exactly match the current native Edit revision"
        )


def _validation_receipt(
    revision_id: str,
    outcome: ValidationOutcome,
) -> dict[str, object]:
    return {
        "revision_id": revision_id,
        "passed": outcome.passed,
        "improved": outcome.improved,
        "summary": outcome.summary,
        "details": thaw_json_object(outcome.details),
        "fingerprint": outcome.fingerprint,
        "code_hash": outcome.code_hash,
        "problem_hash": outcome.problem_hash,
    }


def _budget_signal(session: QualitySession) -> dict[str, int]:
    return {
        "patches_remaining": session.patches_remaining,
        "findings_batches_remaining": session.finding_batches_remaining,
    }


def _json_text(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise TypeError("tool result must be JSON serializable") from error
