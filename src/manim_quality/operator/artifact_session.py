"""Serializable Finding and Revision ledgers for every terminal outcome."""


def findings_payload(session) -> dict[str, object]:
    return {
        "problem_hash": session.problem_hash,
        "findings": [
            {
                "finding_id": item.finding_id,
                "category": item.category.value,
                "severity": item.severity,
                "summary": item.summary,
                "acceptance_criteria": item.acceptance_criteria,
                "depends_on_finding_ids": list(item.depends_on_finding_ids),
                "affected_symbols": list(item.affected_symbols),
                "source_reviewer_ids": list(item.source_reviewer_ids),
            }
            for item in session.findings
        ],
    }


def revisions_payload(session) -> dict[str, object]:
    return {
        "active_revision_id": session.current_revision.revision_id,
        "revisions": [
            {
                "revision_id": item.revision_id,
                "parent_revision_id": item.parent_revision_id,
                "scope": None if item.scope is None else item.scope.value,
                "code_hash": item.code_hash,
                "patch_hash": item.patch_hash,
                "finding_ids": list(item.finding_ids),
            }
            for item in session.attempts
        ],
    }
