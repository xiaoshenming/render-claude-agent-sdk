"""Seven structured MCP tools exposed to the parent and Reviewers."""

from __future__ import annotations

import json

from manim_quality.agents.managed_tools import ManagedToolGrant, ToolEffect
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.revisions.fingerprint import sha256_text

from .models import ValidationOutcome
from .ports import LayoutInspector, RelationChecker, RevisionValidator
from .session import QualitySession
from .source_view import extract_solution
from .tool_contracts import (
    bind_findings,
    bind_patch,
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
) -> tuple[ManagedToolGrant, ...]:
    handlers = _Handlers(
        session,
        relation_checker,
        layout_inspector,
        revision_validator,
    )
    return register_quality_tools(handlers)


class _Handlers:
    def __init__(self, session, relation, layout, validator) -> None:
        self.session = session
        self.relation = relation
        self.layout = layout
        self.validator = validator

    async def read_solution(self, arguments):
        revision_id = bind_revision_id(arguments)
        revision = self.session.get_revision(revision_id)
        self.session.mark_solution_read(revision_id)
        solution = extract_solution(revision.code)
        return _json_text(
            {
                "revision_id": revision.revision_id,
                "code_hash": revision.code_hash,
                "solution_hash": solution.sha256,
                "start_line": solution.start_line,
                "end_line": solution.end_line,
                "source": solution.source,
            }
        )

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

    async def apply_patch(self, arguments):
        values = bind_patch(arguments)
        current = self.session.current_revision
        if values["base_revision_id"] != current.revision_id:
            raise ValueError("base revision is stale")
        if values["base_code_hash"] != current.code_hash:
            raise ValueError("base code hash is stale")
        revision = self.session.apply_patch(
            scope=values["scope"],
            old_text=values["old_text"],
            new_text=values["new_text"],
            finding_ids=values["finding_ids"],
        )
        return _json_text(_patch_receipt(current, revision))

    async def inspect_layout(self, arguments):
        revision = _current_revision(
            self.session,
            bind_revision_id(arguments),
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
        revision = _current_revision(
            self.session,
            bind_revision_id(arguments),
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
        revision = self.session.submit(bind_revision_id(arguments))
        return _json_text(
            {
                "status": "submitted",
                "submitted_revision_id": revision.revision_id,
                "code_hash": revision.code_hash,
                "problem_hash": self.session.problem_hash,
            }
        )


def _patch_receipt(current, revision) -> dict[str, object]:
    return {
        "status": "applied",
        "effect": ToolEffect.REVISION_MUTATION.value,
        "base_revision_id": revision.parent_revision_id,
        "parent_code_hash": current.code_hash,
        "new_revision_id": revision.revision_id,
        "new_code_hash": revision.code_hash,
        "patch_hash": revision.patch_hash,
        "scope": revision.scope.value,
    }


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


def _current_revision(session: QualitySession, revision_id: str):
    current = session.current_revision
    if revision_id != current.revision_id:
        raise ValueError("revision_id is stale")
    return current


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
