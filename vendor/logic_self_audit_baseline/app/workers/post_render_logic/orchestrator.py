"""Orchestrate one bounded post-render logic repair pass."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, Protocol

from app.workers.post_render_logic.evidence import build_logic_evidence
from app.workers.post_render_logic.planning import plan_repairs
from app.workers.post_render_logic.recheck import recheck_issues
from app.workers.post_render_logic.schemas import (
    LogicEvidence,
    LogicRunResult,
    RepairPlan,
    ReviewReport,
)


class LogicReviewer(Protocol):
    def review(self, evidence: LogicEvidence) -> ReviewReport: ...


class LogicCoder(Protocol):
    def patch(self, code: str, plan: RepairPlan) -> Any: ...


class LogicRepairOrchestrator:
    """A small state machine for post-render logic repair candidates.

    The orchestrator performs one review and at most one repair attempt. Recheck
    only evaluates frozen issue predicates from the first review.
    """

    def __init__(
        self,
        *,
        reviewer: LogicReviewer,
        coder: LogicCoder,
        render_again: Callable[[str], Any],
    ) -> None:
        self.reviewer = reviewer
        self.coder = coder
        self.render_again = render_again

    async def run(
        self,
        *,
        code: str,
        job_id: str = "",
        problem_text: str = "",
        expected_answer: str = "",
        constraints: dict[str, Any] | None = None,
        render_meta: dict[str, Any] | None = None,
    ) -> LogicRunResult:
        evidence = build_logic_evidence(
            code=code,
            job_id=job_id,
            problem_text=problem_text,
            expected_answer=expected_answer,
            constraints=constraints,
            render_meta=render_meta,
        )
        review = await _maybe_await(self.reviewer.review(evidence))

        if review.decision == "pass" or not review.issues:
            return LogicRunResult(state="PASS", evidence=evidence, review=review)

        plan = plan_repairs(review.issues)
        if not plan.issue_ids:
            return LogicRunResult(
                state="DEGRADED",
                evidence=evidence,
                review=review,
                plan=plan,
                reason="no safe automatic repair scope",
            )

        fixed_code, attempt = await _maybe_await(self.coder.patch(code, plan))
        render_ok = await _maybe_await(self.render_again(fixed_code))
        if not render_ok:
            return LogicRunResult(
                state="ROLLBACK",
                evidence=evidence,
                review=review,
                plan=plan,
                attempt=attempt,
                fixed_code=fixed_code,
                reason="re-render failed",
            )

        issue_by_id = {issue.issue_id: issue for issue in review.issues}
        frozen_issues = [
            issue_by_id[issue_id]
            for issue_id in plan.issue_ids
            if issue_id in issue_by_id
        ]
        recheck = recheck_issues(fixed_code, frozen_issues)
        state = "FIXED" if recheck.final_decision == "accept_repair" else "DEGRADED"
        return LogicRunResult(
            state=state,
            evidence=evidence,
            review=review,
            plan=plan,
            attempt=attempt,
            recheck=recheck,
            fixed_code=fixed_code,
        )


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
