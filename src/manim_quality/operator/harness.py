"""Single-task orchestration entrypoint for the unified Agent MVP."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path

import anyio

from .agent import QualityOperatorResult
from .artifacts import write_run_artifacts
from .failure_artifacts import write_failed_run_artifacts
from manim_quality.agents._runtime_models import AgentRunFailed
from .gate import GateResult, OuterAcceptanceGate
from .session import QualitySession


@dataclass(frozen=True, slots=True)
class QualityHarnessResult:
    session: QualitySession
    operator_result: QualityOperatorResult
    gate_result: GateResult
    baseline_layout_report: Mapping[str, object]


def _prepared_session_impl(
    inspector,
    problem_text: str,
    candidate_code: str,
    max_patch_attempts: int | None,
) -> tuple[QualitySession, Mapping[str, object]]:
    session = QualitySession(
        problem_text=problem_text,
        candidate_code=candidate_code,
        max_patch_attempts=max_patch_attempts or 12,
    )
    baseline_layout = anyio.run(
        inspector.inspect,
        session.baseline,
        session.problem_hash,
    )
    return session, baseline_layout


class QualityHarness:
    def __init__(
        self,
        *,
        operator,
        relation_checker,
        agent_layout_inspector,
        agent_revision_validator,
        acceptance_layout_inspector,
        acceptance_revision_validator,
    ) -> None:
        if agent_layout_inspector is acceptance_layout_inspector:
            raise ValueError("acceptance layout inspector must be independent")
        if agent_revision_validator is acceptance_revision_validator:
            raise ValueError("acceptance revision validator must be independent")
        self._operator = operator
        self._relation = relation_checker
        self._agent_layout = agent_layout_inspector
        self._agent_validator = agent_revision_validator
        self._gate = OuterAcceptanceGate(
            revision_validator=acceptance_revision_validator,
            layout_inspector=acceptance_layout_inspector,
        )

    def run(
        self,
        *,
        run_id: str,
        workspace: Path,
        artifact_root: Path,
        problem_text: str,
        candidate_code: str,
        estimated_input_tokens: int,
        reserved_output_tokens: int,
        reserved_cache_read_tokens: int = 0,
        reserved_cache_write_tokens: int = 0,
        max_patch_attempts: int | None = None,
    ) -> QualityHarnessResult:
        session, baseline_layout = _prepared_session_impl(
            self._agent_layout,
            problem_text,
            candidate_code,
            max_patch_attempts,
        )
        try:
            operator_result = self._operator.run(
                run_id=run_id,
                workspace=workspace,
                session=session,
                relation_checker=self._relation,
                layout_inspector=self._agent_layout,
                revision_validator=self._agent_validator,
                estimated_input_tokens=estimated_input_tokens,
                reserved_output_tokens=reserved_output_tokens,
                reserved_cache_read_tokens=reserved_cache_read_tokens,
                reserved_cache_write_tokens=reserved_cache_write_tokens,
            )
        except AgentRunFailed as error:
            write_failed_run_artifacts(
                root=artifact_root,
                session=session,
                record=error.record,
                baseline_layout_report=baseline_layout,
                error=error,
            )
            raise
        gate_result = anyio.run(self._gate.evaluate, session)
        write_run_artifacts(
            root=artifact_root,
            session=session,
            operator_result=operator_result,
            gate_result=gate_result,
            baseline_layout_report=baseline_layout,
        )
        return QualityHarnessResult(
            session=session,
            operator_result=operator_result,
            gate_result=gate_result,
            baseline_layout_report=baseline_layout,
        )
