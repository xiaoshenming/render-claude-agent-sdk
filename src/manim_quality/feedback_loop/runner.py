from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .models import (
    AssuranceOutcome,
    Candidate,
    LoopExecutionIdentity,
    LoopResult,
    LoopState,
    PassRecord,
)
from .policy import better_grade, is_accepted, is_repairable, stable_issues
from .store import JsonLoopStore


class CoderPort(Protocol):
    def repair(
        self,
        candidate: Candidate,
        issues: tuple[dict[str, object], ...],
        repair_round: int,
    ) -> Candidate: ...


class AssurancePort(Protocol):
    def review(
        self, candidate: Candidate, assurance_pass: int
    ) -> AssuranceOutcome: ...


class FeedbackLoopRunner:
    def __init__(
        self,
        *,
        coder: CoderPort,
        assurance: AssurancePort,
        store: JsonLoopStore,
        max_assurance_passes: int = 3,
        tts_mode: str = "disabled",
    ) -> None:
        if max_assurance_passes != 3:
            raise ValueError("feedback loop policy requires exactly three passes")
        self.coder = coder
        self.assurance = assurance
        self.store = store
        self.max_passes = max_assurance_passes
        self.tts_mode = tts_mode

    def run(
        self,
        initial: Candidate,
        *,
        identity: LoopExecutionIdentity | None = None,
        bootstrap: bool = False,
        resume: bool = False,
    ) -> LoopResult:
        state = self.store.load() if resume else None
        if state is not None:
            _require_matching_identity(state, identity)
        else:
            _require_initial_identity(initial, identity)
            state = LoopState.initial(initial, identity)
            self.store.save(state)
        if resume and state.terminal_reason in {"assurance_error", "coder_error"}:
            state = replace(state, terminal_reason=None)
            self.store.save(state)
        if state.terminal_reason:
            return _result(state)
        if bootstrap and not state.bootstrap_completed:
            state = self._bootstrap(state)
            if state.terminal_reason:
                return _result(state)
        while state.assurance_passes < self.max_passes:
            state = self._assure(state)
            if state.terminal_reason:
                break
            if state.assurance_passes >= self.max_passes:
                state = self._finish(state, "assurance_budget_exhausted")
                break
            state = self._repair(state)
            if state.terminal_reason:
                break
        return _result(state)

    def _bootstrap(self, state: LoopState) -> LoopState:
        state = replace(state, coder_calls=state.coder_calls + 1)
        self.store.save(state)
        try:
            candidate = self.coder.repair(state.current_candidate, (), 0)
        except Exception:
            return self._finish(state, "coder_error")
        state = replace(
            state,
            current_candidate=candidate,
            best_candidate=candidate,
            bootstrap_completed=True,
        )
        self.store.save(state)
        return state

    def _assure(self, state: LoopState) -> LoopState:
        number = state.assurance_passes + 1
        try:
            outcome = self.assurance.review(state.current_candidate, number)
        except Exception:
            return self._finish(state, "assurance_error")
        issues = stable_issues(
            outcome,
            candidate=state.current_candidate,
            assurance_pass=number,
            tts_mode=self.tts_mode,
        )
        record = PassRecord(number, state.current_candidate, outcome)
        score = _issue_score(issues)
        improved = better_grade(state.best_grade, outcome.grade)
        same_grade_better = (
            state.best_grade == outcome.grade
            and (state.best_issue_score is None or score < state.best_issue_score)
        )
        selected = improved or same_grade_better
        state = replace(
            state,
            assurance_passes=number,
            records=state.records + (record,),
            pending_issues=issues,
            best_grade=outcome.grade if selected else state.best_grade,
            best_issue_score=score if selected else state.best_issue_score,
            best_candidate=(
                state.current_candidate if selected else state.best_candidate
            ),
        )
        self.store.save(state)
        if is_accepted(outcome.grade):
            return self._finish(state, "accepted_grade")
        if not is_repairable(outcome.grade):
            return self._finish(state, "non_repairable_grade")
        if not issues:
            return self._finish(state, "no_repairable_issues")
        return state

    def _repair(self, state: LoopState) -> LoopState:
        repair_round = state.repair_rounds + 1
        state = replace(state, coder_calls=state.coder_calls + 1)
        self.store.save(state)
        try:
            candidate = self.coder.repair(
                state.current_candidate,
                state.pending_issues,
                repair_round,
            )
        except Exception:
            return self._finish(state, "coder_error")
        if candidate.source_sha256 == state.current_candidate.source_sha256:
            return self._finish(state, "duplicate_candidate")
        state = replace(
            state,
            current_candidate=candidate,
            repair_rounds=repair_round,
            pending_issues=(),
        )
        self.store.save(state)
        return state

    def _finish(self, state: LoopState, reason: str) -> LoopState:
        state = replace(state, terminal_reason=reason, pending_issues=())
        self.store.save(state)
        return state


def _result(state: LoopState) -> LoopResult:
    return LoopResult(
        final_candidate=state.best_candidate,
        final_grade=state.best_grade,
        assurance_passes=state.assurance_passes,
        repair_rounds=state.repair_rounds,
        coder_calls=state.coder_calls,
        terminal_reason=state.terminal_reason or "assurance_budget_exhausted",
        records=state.records,
    )


def _issue_score(issues: tuple[dict[str, object], ...]) -> tuple[int, int]:
    high = sum(
        1
        for issue in issues
        if str(issue.get("severity", "")).lower() in {"blocking", "critical", "high"}
    )
    return high, len(issues)


def _require_matching_identity(
    state: LoopState,
    expected: LoopExecutionIdentity | None,
) -> None:
    actual = state.execution_identity
    if actual != expected:
        raise ValueError("feedback loop execution identity mismatch")


def _require_initial_identity(
    initial: Candidate,
    identity: LoopExecutionIdentity | None,
) -> None:
    if identity is None:
        return
    if (
        identity.source_sha256 != initial.source_sha256
        or identity.video_sha256 != initial.video_sha256
    ):
        raise ValueError("feedback loop execution identity mismatch")
