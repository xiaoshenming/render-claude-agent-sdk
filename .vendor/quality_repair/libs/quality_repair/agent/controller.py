"""agent.controller — 进展驱动止损循环。

进展信号只看 CheckerAdapter 复检的 blocking 数值；LLM 自述一律无效。
结束时强制把最优快照写回 workdir，永不把更差代码留在 workdir（D4 红线）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from ..core_candidate_view import compose_core_candidate, core_candidate_enabled
from ..interfaces import CheckerAdapter
from ..schemas import AgentRunReport, Budget, CheckResult
from .diagnostic_protocol import (
    ACTION_FIX,
    ACTION_NEED_MORE_EVIDENCE,
    ACTION_NO_FIX,
    parse_agent_decision,
)
from .evidence_query import materialize_evidence_requests


class _AgentRunner(Protocol):
    """Internal runner contract. Public repair() always supplies ClaudeSDKRunner."""

    name: str

    def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport: ...


@dataclass(kw_only=True)
class LoopResult:
    final_code: str
    changed: bool
    rounds_used: int
    tokens_used: int
    best_check: CheckResult
    stop_reason: str  # zero_blocking|no_progress|same_signature|token_cap|round_cap|runner_error_*|check_error_*
    rounds: list[dict] = field(default_factory=list)


@dataclass(kw_only=True)
class _LoopState:
    """循环内部可变状态，避免万能 dict 穿层。"""

    input_code: str
    best_code: str
    best_check: CheckResult
    best_blocking: int
    tokens_used: int = 0
    no_progress: int = 0
    rounds_used: int = 0
    stop_reason: str = "round_cap"
    rounds: list[dict] = field(default_factory=list)
    sig_counts: dict[str, int] = field(default_factory=dict)
    decision_parse_errors: int = 0
    evidence_only_rounds: int = 0


def _record_best(state: _LoopState, code: str, check: CheckResult) -> None:
    state.best_code = code
    state.best_check = check
    state.best_blocking = check.blocking_count


_RISK_ONLY_CATEGORIES = {
    "label_shape_overlap_risk",
}


def _evaluate_round(
    state: _LoopState, candidate: Path, check: CheckResult, budget: Budget, is_last: bool
) -> bool:
    """更新 best 与止损计数，返回是否应停止。"""
    blocking = check.blocking_count
    if blocking == 0:
        _record_best(state, candidate.read_text(encoding="utf-8"), check)
        state.stop_reason = "zero_blocking"
        return True

    improved = blocking < state.best_blocking
    if improved:
        previous_best = state.best_blocking
        _record_best(state, candidate.read_text(encoding="utf-8"), check)
        state.no_progress = 0
        if not is_last and _should_accept_degraded_round(previous_best=previous_best, check=check, budget=budget):
            state.stop_reason = "accepted_degraded_low_residual"
            return True
    else:
        state.no_progress += 1

    sig = check.signature
    state.sig_counts[sig] = state.sig_counts.get(sig, 0) + 1
    if state.sig_counts[sig] >= budget.same_signature_stop:
        state.stop_reason = "same_signature"
        return True
    if state.no_progress >= budget.no_progress_stop:
        state.stop_reason = "no_progress"
        return True
    if not improved and state.tokens_used > budget.token_hard_cap:
        state.stop_reason = "token_cap"
        return True
    if is_last:
        state.stop_reason = "round_cap"
        return True
    return False


def _should_accept_degraded_round(*, previous_best: int, check: CheckResult, budget: Budget) -> bool:
    """Stop before another costly SDK round when the remaining layout risk is already low.

    The final acceptance judge still decides SUCCESS_DEGRADED versus rollback.
    This only prevents a second speculative repair round after a real improvement.
    """
    after = check.blocking_count
    if previous_best <= 0 or after <= 0 or after >= previous_best:
        return False
    reduction_ratio = (previous_best - after) / previous_best
    if (
        budget.accept_degraded_max_blocking is not None
        and after <= budget.accept_degraded_max_blocking
        and reduction_ratio >= budget.accept_degraded_min_reduction_ratio
    ):
        return True
    if budget.accept_risk_only_max_blocking is None or after > budget.accept_risk_only_max_blocking:
        return False
    categories = _issue_categories(check.issues)
    return bool(categories) and categories.issubset(_RISK_ONLY_CATEGORIES)


def _issue_categories(issues: list[dict[str, Any]]) -> set[str]:
    categories: set[str] = set()
    for issue in issues:
        value = issue.get("category") or issue.get("kind") or issue.get("type")
        if value:
            categories.add(str(value))
    return categories


def run_repair_loop(
    *,
    workdir: Path,
    prompt: str | Callable[[Path, int], str],
    runner: _AgentRunner,
    checker: CheckerAdapter,
    budget: Budget,
    initial_check: CheckResult,
    after_check: Callable[[Path, CheckResult], None] | None = None,
) -> LoopResult:
    """执行止损循环。任何内部异常均捕获并回退输入代码，绝不上抛。"""
    candidate = workdir / "candidate.py"
    try:
        input_code = candidate.read_text(encoding="utf-8")
    except OSError as exc:
        return LoopResult(
            final_code="",
            changed=False,
            rounds_used=0,
            tokens_used=0,
            best_check=CheckResult.failure(f"candidate_unreadable:{exc}"),
            stop_reason="check_error",
            rounds=[],
        )
    state = _LoopState(
        input_code=input_code,
        best_code=input_code,
        best_check=initial_check,
        best_blocking=initial_check.blocking_count,
    )
    try:
        for round_no in range(1, budget.max_rounds + 1):
            state.rounds_used = round_no
            before_code = state.best_code
            before_blocking = state.best_blocking
            core_before_code = _read_core_candidate_if_enabled(workdir)
            round_prompt = prompt(workdir, round_no) if callable(prompt) else prompt
            prompt_path = workdir / f"prompt_round_{round_no:02d}.md"
            prompt_path.write_text(round_prompt, encoding="utf-8")
            report = runner.run(workdir, round_prompt, budget)
            state.tokens_used += report.tokens_used
            compose_report = _compose_core_view_if_enabled(workdir)
            core_attempted_code = _read_core_candidate_if_enabled(workdir)
            attempted_code = candidate.read_text(encoding="utf-8")
            attempted_changed = attempted_code != before_code
            decision = parse_agent_decision(report.final_text)
            if compose_report and not compose_report.get("enabled"):
                state.stop_reason = "compose_error_after_edit"
                state.rounds.append(
                    _round_row(
                        round_no,
                        report.changed,
                        report.tokens_used,
                        None,
                        None,
                        accepted=False,
                        before_blocking=before_blocking,
                        base_code=before_code,
                        attempted_code=attempted_code,
                        prompt_text=round_prompt,
                        usage=report.usage,
                        agent_decision=decision.to_dict(),
                        final_text=report.final_text,
                        error=str(compose_report.get("reason") or "compose_failed"),
                        error_class="compose_error_after_edit",
                        compose_report=compose_report,
                        core_base_code=core_before_code,
                        core_attempted_code=core_attempted_code,
                    )
                )
                break
            if report.error:
                report.changed = attempted_changed
                if not report.changed:
                    state.stop_reason = "runner_error_no_edit"
                    state.rounds.append(
                        _round_row(
                            round_no,
                            False,
                            report.tokens_used,
                            None,
                            None,
                            accepted=False,
                            before_blocking=before_blocking,
                            base_code=before_code,
                            attempted_code=attempted_code,
                            prompt_text=round_prompt,
                            usage=report.usage,
                            agent_decision=decision.to_dict(),
                            final_text=report.final_text,
                            error=report.error,
                            error_class="runner_error_no_edit",
                            compose_report=compose_report,
                            core_base_code=core_before_code,
                            core_attempted_code=core_attempted_code,
                        )
                    )
                    break
            if not attempted_changed:
                if _handle_no_edit_round(
                    state=state,
                    workdir=workdir,
                    round_no=round_no,
                    decision=decision,
                    report=report,
                    before_blocking=before_blocking,
                    before_code=before_code,
                    attempted_code=attempted_code,
                    round_prompt=round_prompt,
                    budget=budget,
                    is_last=round_no >= budget.max_rounds,
                    compose_report=compose_report,
                    core_base_code=core_before_code,
                    core_attempted_code=core_attempted_code,
                ):
                    break
                continue
            check = checker.run_check(candidate, workdir)
            if not check.ok:
                # checker 本身失败：不采纳本轮，保留既有 best 快照
                state.stop_reason = "check_error_after_edit" if attempted_changed else "check_error_no_edit"
                state.rounds.append(
                    _round_row(
                        round_no,
                        report.changed,
                        report.tokens_used,
                        check.blocking_count,
                        check.signature,
                        accepted=False,
                        before_blocking=before_blocking,
                        base_code=before_code,
                        attempted_code=attempted_code,
                        prompt_text=round_prompt,
                        usage=report.usage,
                        agent_decision=decision.to_dict(),
                        final_text=report.final_text,
                        check_after=check.to_dict(),
                        error=check.error,
                        error_class=state.stop_reason,
                        compose_report=compose_report,
                        core_base_code=core_before_code,
                        core_attempted_code=core_attempted_code,
                    )
                )
                break
            accepted = check.blocking_count == 0 or check.blocking_count < before_blocking
            state.rounds.append(
                _round_row(
                    round_no,
                    report.changed,
                    report.tokens_used,
                    check.blocking_count,
                    check.signature,
                    accepted=accepted,
                    before_blocking=before_blocking,
                    base_code=before_code,
                    attempted_code=attempted_code,
                    prompt_text=round_prompt,
                    usage=report.usage,
                    agent_decision=decision.to_dict(),
                    final_text=report.final_text,
                    check_after=check.to_dict(),
                    error=report.error,
                    error_class=_edit_round_error_class(report_error=report.error, decision_valid=decision.valid, accepted=accepted),
                    compose_report=compose_report,
                    core_base_code=core_before_code,
                    core_attempted_code=core_attempted_code,
                )
            )
            if accepted and after_check:
                after_check(workdir, check)
            if not accepted:
                candidate.write_text(state.best_code, encoding="utf-8")
                _rebuild_core_view_from_full_candidate(workdir)
            if _evaluate_round(state, candidate, check, budget, round_no >= budget.max_rounds):
                break
    except Exception as exc:  # 层边界：把异常变成结构化结果
        state.best_code = input_code
        state.best_check = CheckResult.failure(f"loop_exception:{exc}")
        state.stop_reason = "check_error"

    candidate.write_text(state.best_code, encoding="utf-8")
    if core_candidate_enabled(workdir):
        build_best = _rebuild_core_view_from_full_candidate(workdir)
        if build_best and not build_best.get("enabled"):
            state.rounds.append(
                {
                    "round": state.rounds_used,
                    "changed": False,
                    "attempted_changed": False,
                    "accepted": False,
                    "before_blocking": state.best_blocking,
                    "after_blocking": state.best_blocking,
                    "tokens": 0,
                    "blocking": state.best_blocking,
                    "signature": state.best_check.signature,
                    "base_code": state.best_code,
                    "attempted_code": state.best_code,
                    "usage": {},
                    "error_class": "core_view_rebuild_failed",
                    "error": str(build_best.get("reason") or "unknown"),
                    "compose_report": build_best,
                }
            )
    return LoopResult(
        final_code=state.best_code,
        changed=state.best_code != input_code,
        rounds_used=state.rounds_used,
        tokens_used=state.tokens_used,
        best_check=state.best_check,
        stop_reason=state.stop_reason,
        rounds=state.rounds,
    )


def _compose_core_view_if_enabled(workdir: Path) -> dict[str, Any] | None:
    if not core_candidate_enabled(workdir):
        return None
    return compose_core_candidate(workdir).to_dict()


def _rebuild_core_view_from_full_candidate(workdir: Path) -> dict[str, Any] | None:
    try:
        from ..core_candidate_view import build_core_candidate_view

        return build_core_candidate_view(workdir).to_dict()
    except Exception as exc:  # noqa: BLE001 - final rollback sync must not escape loop boundary
        return {"enabled": False, "reason": f"core_view_rebuild_exception:{exc}"}


def _read_core_candidate_if_enabled(workdir: Path) -> str | None:
    if not core_candidate_enabled(workdir):
        return None
    try:
        return (workdir / "core_candidate.py").read_text(encoding="utf-8")
    except OSError:
        return None


def _handle_no_edit_round(
    *,
    state: _LoopState,
    workdir: Path,
    round_no: int,
    decision: Any,
    report: AgentRunReport,
    before_blocking: int,
    before_code: str,
    attempted_code: str,
    round_prompt: str,
    budget: Budget,
    is_last: bool,
    compose_report: dict[str, Any] | None = None,
    core_base_code: str | None = None,
    core_attempted_code: str | None = None,
) -> bool:
    """Handle structured no-edit control-plane decisions.

    Returns True when the loop should stop.
    """
    if not decision.valid:
        state.decision_parse_errors += 1
        state.stop_reason = "agent_decision_parse_error"
        state.rounds.append(
            _round_row(
                round_no,
                False,
                report.tokens_used,
                None,
                None,
                accepted=False,
                before_blocking=before_blocking,
                base_code=before_code,
                attempted_code=attempted_code,
                prompt_text=round_prompt,
                usage=report.usage,
                agent_decision=decision.to_dict(),
                final_text=report.final_text,
                error=decision.parse_error,
                error_class="agent_decision_parse_error",
                compose_report=compose_report,
                core_base_code=core_base_code,
                core_attempted_code=core_attempted_code,
            )
        )
        return state.decision_parse_errors > 1 or is_last or state.tokens_used > budget.token_hard_cap

    if decision.action == ACTION_NO_FIX:
        state.stop_reason = "agent_no_fix"
        state.rounds.append(
            _round_row(
                round_no,
                False,
                report.tokens_used,
                None,
                None,
                accepted=False,
                before_blocking=before_blocking,
                base_code=before_code,
                attempted_code=attempted_code,
                prompt_text=round_prompt,
                usage=report.usage,
                agent_decision=decision.to_dict(),
                final_text=report.final_text,
                compose_report=compose_report,
                core_base_code=core_base_code,
                core_attempted_code=core_attempted_code,
            )
        )
        return True

    if decision.action == ACTION_NEED_MORE_EVIDENCE:
        state.evidence_only_rounds += 1
        if not decision.evidence_requests:
            state.stop_reason = "agent_invalid_evidence_request"
            evidence_report: dict[str, Any] | None = None
            error = "need_more_evidence_without_requests"
            error_class = "agent_invalid_evidence_request"
        else:
            evidence_report = materialize_evidence_requests(
                workdir=workdir,
                round_no=round_no,
                requests=decision.evidence_requests,
            )
            error = None
            error_class = None
            if not evidence_report.get("results"):
                state.stop_reason = "agent_invalid_evidence_request"
                error = "no_evidence_queries_materialized"
                error_class = "agent_invalid_evidence_request"
        state.rounds.append(
            _round_row(
                round_no,
                False,
                report.tokens_used,
                None,
                None,
                accepted=False,
                before_blocking=before_blocking,
                base_code=before_code,
                attempted_code=attempted_code,
                prompt_text=round_prompt,
                usage=report.usage,
                agent_decision=decision.to_dict(),
                evidence_query=evidence_report,
                final_text=report.final_text,
                error=error,
                error_class=error_class,
                compose_report=compose_report,
                core_base_code=core_base_code,
                core_attempted_code=core_attempted_code,
            )
        )
        if error_class:
            return True
        if state.evidence_only_rounds >= 2:
            state.stop_reason = "agent_evidence_loop"
            return True
        if state.tokens_used > budget.token_hard_cap:
            state.stop_reason = "token_cap"
            return True
        if is_last:
            state.stop_reason = "round_cap"
            return True
        return False

    if decision.action == ACTION_FIX:
        state.stop_reason = "runner_error_fix_without_edit"
        state.rounds.append(
            _round_row(
                round_no,
                False,
                report.tokens_used,
                None,
                None,
                accepted=False,
                before_blocking=before_blocking,
                base_code=before_code,
                attempted_code=attempted_code,
                prompt_text=round_prompt,
                usage=report.usage,
                agent_decision=decision.to_dict(),
                final_text=report.final_text,
                error="agent_declared_fix_without_edit",
                error_class="runner_error_fix_without_edit",
                compose_report=compose_report,
                core_base_code=core_base_code,
                core_attempted_code=core_attempted_code,
            )
        )
        return True

    state.stop_reason = "agent_unknown_action"
    return True


def _edit_round_error_class(*, report_error: str | None, decision_valid: bool, accepted: bool) -> str | None:
    if report_error:
        return "runner_error_after_edit"
    if not decision_valid:
        return "accepted_unstructured_decision" if accepted else "unstructured_decision_after_edit"
    return None


def _round_row(
    round_no: int,
    changed: bool,
    tokens: int,
    blocking: int | None,
    signature: str | None,
    *,
    accepted: bool,
    before_blocking: int | None,
    base_code: str | None,
    attempted_code: str | None,
    prompt_text: str | None = None,
    usage: dict[str, Any] | None = None,
    agent_decision: dict[str, Any] | None = None,
    evidence_query: dict[str, Any] | None = None,
    final_text: str | None = None,
    check_after: dict[str, Any] | None = None,
    error: str | None = None,
    error_class: str | None = None,
    compose_report: dict[str, Any] | None = None,
    core_base_code: str | None = None,
    core_attempted_code: str | None = None,
) -> dict:
    attempted_changed = None
    if base_code is not None and attempted_code is not None:
        attempted_changed = attempted_code != base_code
    row = {
        "round": round_no,
        "changed": changed,
        "attempted_changed": attempted_changed,
        "accepted": accepted,
        "before_blocking": before_blocking,
        "after_blocking": blocking,
        "tokens": tokens,
        "blocking": blocking,
        "signature": signature,
        "base_code": base_code,
        "attempted_code": attempted_code,
        "prompt_text": prompt_text,
        "usage": dict(usage or {}),
    }
    if agent_decision is not None:
        row["agent_decision"] = agent_decision
    if evidence_query is not None:
        row["evidence_query"] = evidence_query
    if final_text is not None:
        row["final_text"] = final_text
    if check_after is not None:
        row["check_after"] = check_after
    if error_class:
        row["error_class"] = error_class
    if error:
        row["error"] = error
    if compose_report is not None:
        row["compose_report"] = compose_report
    if core_base_code is not None:
        row["core_base_code"] = core_base_code
    if core_attempted_code is not None:
        row["core_attempted_code"] = core_attempted_code
    return row
