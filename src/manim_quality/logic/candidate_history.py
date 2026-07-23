"""Keep the strongest usable AI candidate across repair attempts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._repair_flow_models import AttemptOutcome, LogicRepairFlowResult
from .candidate_policy import risk_result


@dataclass(slots=True)
class CandidateHistory:
    code: str | None = None
    resolved_issue_ids: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()

    def consider(self, outcome: AttemptOutcome) -> None:
        if not outcome.candidate_code:
            return
        resolved = tuple(outcome.resolved_issue_ids)
        if self.code is None or len(resolved) > len(self.resolved_issue_ids):
            self.code = outcome.candidate_code
            self.resolved_issue_ids = resolved
            self.risks = tuple(outcome.review_gaps)

    def preserve(
        self,
        candidate: Path,
        hashes: list[str],
        attempt: int,
        fallback_reason: str,
    ) -> LogicRepairFlowResult | None:
        if self.code is None:
            return None
        risks = "; ".join(self.risks)
        reason = risks or fallback_reason
        return risk_result(candidate, hashes, attempt, self.code, reason)
