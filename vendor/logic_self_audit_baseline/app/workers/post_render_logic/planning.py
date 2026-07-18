"""Convert frozen logic issues into minimal repair plans."""

from __future__ import annotations

import hashlib

from app.workers.post_render_logic.schemas import LogicIssue, RepairPlan

_AUTO_REPAIR_SCOPES = {
    "text_claim_only",
    "formula_claim_only",
    "scene_logic",
    "code_claim_binding",
}

_BASE_FORBIDDEN_CHANGES = [
    "no BaseConfigScene/header/helper edits",
    "no layout/overlap edits",
    "no unrelated wording improvements",
    "no new solution method",
    "no unrelated Scene edits",
]


def plan_repairs(issues: list[LogicIssue]) -> RepairPlan:
    """Build one conservative repair plan from a frozen issue ledger."""
    repairable = [
        issue
        for issue in issues
        if issue.repairable
        and issue.repair_scope in _AUTO_REPAIR_SCOPES
        and issue.target_scene_ids
    ]
    if not repairable:
        return RepairPlan(
            plan_id="repair-plan-record-only",
            issue_ids=[],
            repair_scope="record_only",
            target_scene_ids=[],
            allowed_edit_regions=[],
            repair_strategy="record issue only; no safe automatic repair scope",
            forbidden_changes=_BASE_FORBIDDEN_CHANGES,
            acceptance_predicates=[],
            fallback="mark_degraded_no_repair",
        )

    issue = repairable[0]
    return RepairPlan(
        plan_id=_plan_id(issue),
        issue_ids=[issue.issue_id],
        repair_scope=issue.repair_scope,
        target_scene_ids=list(issue.target_scene_ids),
        allowed_edit_regions=[
            {
                "artifact": "scene_code",
                "scene_id": scene_id,
                "symbols": ["class_body"],
            }
            for scene_id in issue.target_scene_ids
        ],
        repair_strategy=_strategy_for(issue),
        forbidden_changes=_BASE_FORBIDDEN_CHANGES,
        acceptance_predicates=list(issue.acceptance_predicates),
        max_coder_attempts=1,
        fallback="mark_degraded_no_repair",
    )


def _plan_id(issue: LogicIssue) -> str:
    raw = f"{issue.issue_id}:{issue.issue_type}:{','.join(issue.target_scene_ids)}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
    return f"repair-plan-{digest}"


def _strategy_for(issue: LogicIssue) -> str:
    if issue.repair_scope == "formula_claim_only":
        return "replace incorrect formula/answer claim only"
    if issue.repair_scope == "text_claim_only":
        return "replace incorrect text claim only"
    if issue.repair_scope == "code_claim_binding":
        return "align code-bound claim with frozen issue evidence"
    return "repair target scene logic with the smallest safe edit"
