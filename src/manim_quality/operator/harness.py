"""Single-task orchestration entrypoint for the unified Agent MVP."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import anyio

from .agent import QualityOperatorResult
from .artifacts import write_run_artifacts
from .gate import GateResult, OuterAcceptanceGate
from .session import QualitySession


@dataclass(frozen=True, slots=True)
class QualityHarnessResult:
    session: QualitySession
    operator_result: QualityOperatorResult
    gate_result: GateResult


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
    ) -> QualityHarnessResult:
        session = QualitySession(
            problem_text=problem_text,
            candidate_code=candidate_code,
        )
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
        gate_result = anyio.run(self._gate.evaluate, session)
        write_run_artifacts(
            root=artifact_root,
            session=session,
            operator_result=operator_result,
            gate_result=gate_result,
        )
        return QualityHarnessResult(
            session=session,
            operator_result=operator_result,
            gate_result=gate_result,
        )
