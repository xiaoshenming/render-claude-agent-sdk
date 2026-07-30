from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from .models import (
    AssuranceOutcome,
    Candidate,
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

    def run(self, initial: Candidate, *, resume: bool = False) -> LoopResult:
        state = self.store.load() if resume else None
        state = state or LoopState.initial(initial)
        if resume and state.terminal_reason in {"assurance_error", "coder_error"}:
            state = replace(state, terminal_reason=None)
            self.store.save(state)
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
        improved = better_grade(state.best_grade, outcome.grade)
        state = replace(
            state,
            assurance_passes=number,
            records=state.records + (record,),
            pending_issues=issues,
            best_grade=outcome.grade if improved else state.best_grade,
            best_candidate=(
                state.current_candidate if improved else state.best_candidate
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
        terminal_reason=state.terminal_reason or "assurance_budget_exhausted",
        records=state.records,
    )
