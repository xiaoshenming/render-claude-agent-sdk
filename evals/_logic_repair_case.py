"""Execute one frozen logic repair case from persisted Reviewer evidence."""

from __future__ import annotations

import json
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import __version__ as sdk_version

from manim_quality.agents import (
    AgentRuntime,
    BudgetLimits,
    ClaudeSdkBackend,
    coder_profile,
    verifier_profile,
)
from manim_quality.logic._scene_evidence import extract_scenes
from manim_quality.logic.coder import LogicCoder
from manim_quality.logic.eval_manifest import FrozenEvalCase
from manim_quality.logic.repair_flow import LogicRepairFlow, RepairFlowStatus
from manim_quality.logic.repair_plan import build_repair_plan
from manim_quality.logic.reporting import review_report_from_dict
from manim_quality.logic.schemas import LogicDecision
from manim_quality.logic.verifier import DirectedVerifier
from manim_quality.revisions.fingerprint import code_hash

from ._logic_repair_metrics import (
    RepairCaseMetrics,
    RoleUsageMetrics,
    target_lines_restored,
)
from ._logic_shadow_io import JsonSequenceUsageSink, write_json

RESERVED_OUTPUT_TOKENS = 40_000


@dataclass(frozen=True, slots=True)
class RepairRunConfig:
    model: str
    provider_env: Mapping[str, str]
    review_root: Path
    output_root: Path


def run_repair_case(
    case: FrozenEvalCase, *, dataset_root: Path, config: RepairRunConfig
) -> RepairCaseMetrics:
    started = time.monotonic()
    case_dir = _case_dir(config.output_root, case.sample_id)
    coder_sink = JsonSequenceUsageSink(case_dir, "coder")
    verifier_sink = JsonSequenceUsageSink(case_dir, "verifier")
    decision = "error"
    attempted = False
    status = "not_attempted"
    attempts = 0
    target_restored: bool | None = None
    over_edit = False
    error: str | None = None
    try:
        report = _review_report(config.review_root, case.sample_id)
        decision = report.decision.value
        if report.decision is not LogicDecision.NEEDS_REPAIR:
            metrics = _metrics(
                case,
                decision,
                False,
                status,
                0,
                None,
                False,
                coder_sink,
                verifier_sink,
                started,
                None,
            )
            write_json(case_dir / "repair_result.json", metrics.to_dict())
            return metrics
        attempted = True
        workspace = _workspace(case_dir)
        source = _required(case, "candidate.py", dataset_root)
        candidate = workspace / "candidate.py"
        shutil.copyfile(source, candidate)
        baseline = candidate.read_text(encoding="utf-8")
        plan = build_repair_plan(report, extract_scenes(baseline))
        flow = _flow(config, coder_sink, verifier_sink)
        estimate = max(1_000, len(baseline.encode("utf-8")) // 2)
        result = flow.run(
            run_id=f"repair-{case.sample_id}",
            plan=plan,
            workspace=workspace,
            candidate_path=candidate,
            coder_estimated_input_tokens=estimate,
            coder_reserved_output_tokens=RESERVED_OUTPUT_TOKENS,
            verifier_estimated_input_tokens=estimate,
            verifier_reserved_output_tokens=RESERVED_OUTPUT_TOKENS,
        )
        status = result.status.value
        attempts = result.attempt_count
        patched = candidate.read_text(encoding="utf-8")
        if result.status is RepairFlowStatus.CANDIDATE_READY:
            shutil.copyfile(candidate, case_dir / "candidate_after.py")
        if case.truth.value == "known_bad":
            original = _required(case, "original_candidate.py", dataset_root)
            target_restored = target_lines_restored(
                baseline,
                patched,
                original.read_text(encoding="utf-8"),
                case.target_lines,
            )
        else:
            over_edit = code_hash(patched) != code_hash(baseline)
    except Exception as caught:
        error = f"{type(caught).__name__}: {caught}"
        status = "error"
    metrics = _metrics(
        case,
        decision,
        attempted,
        status,
        attempts,
        target_restored,
        over_edit,
        coder_sink,
        verifier_sink,
        started,
        error,
    )
    write_json(case_dir / "repair_result.json", metrics.to_dict())
    return metrics


def _flow(config, coder_sink, verifier_sink) -> LogicRepairFlow:
    backend = ClaudeSdkBackend(provider_env=config.provider_env)
    tool_version = f"claude-agent-sdk-{sdk_version}"
    coder = LogicCoder(
        AgentRuntime(backend, coder_sink, _limits(max_turns=5)),
        coder_profile(
            model=config.model,
            prompt_version="logic-coder-v1",
            tool_version=f"{tool_version}-read-edit-v1",
        ),
    )
    verifier = DirectedVerifier(
        AgentRuntime(backend, verifier_sink, _limits(max_turns=4)),
        verifier_profile(
            model=config.model,
            prompt_version="logic-verifier-v1",
            tool_version=f"{tool_version}-read-v1",
        ),
    )
    return LogicRepairFlow(coder, verifier)


def _review_report(root: Path, sample_id: str):
    path = (_case_dir(root, sample_id) / "review_report.json").resolve(strict=True)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("review report must be an object")
    return review_report_from_dict(payload)


def _metrics(
    case,
    decision,
    attempted,
    status,
    attempts,
    restored,
    over_edit,
    coder_sink,
    verifier_sink,
    started,
    error,
) -> RepairCaseMetrics:
    return RepairCaseMetrics(
        case.sample_id,
        case.truth.value,
        decision,
        attempted,
        status,
        attempts,
        restored,
        over_edit,
        _role_usage(coder_sink.records),
        _role_usage(verifier_sink.records),
        int((time.monotonic() - started) * 1_000),
        error,
    )


def _role_usage(records) -> RoleUsageMetrics:
    return RoleUsageMetrics(
        calls=len(records),
        input_tokens=sum(record.usage.input_tokens for record in records),
        output_tokens=sum(record.usage.output_tokens for record in records),
        cache_read_tokens=sum(record.usage.cache_read_tokens for record in records),
        cache_write_tokens=sum(record.usage.cache_write_tokens for record in records),
        turns=sum(record.turns for record in records),
        model_rounds=sum(record.observed_model_rounds for record in records),
        elapsed_ms=sum(record.elapsed_ms for record in records),
    )


def _workspace(case_dir: Path) -> Path:
    workspace = case_dir / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    return workspace


def _case_dir(root: Path, sample_id: str) -> Path:
    base = (Path(root).resolve() / "cases").resolve()
    path = (base / sample_id).resolve()
    if not path.is_relative_to(base):
        raise ValueError("case path escapes root")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _required(case: FrozenEvalCase, name: str, root: Path) -> Path:
    artifact = case.artifacts.get(name)
    if artifact is None:
        raise ValueError(f"missing required artifact: {name}")
    return artifact.resolve_verified(root)


def _limits(*, max_turns: int) -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=250_000,
        max_turns=max_turns,
        max_tool_calls=8,
        max_elapsed_ms=240_000,
        max_input_tokens=80_000,
        max_output_tokens=50_000,
        max_cache_read_tokens=80_000,
        max_cache_write_tokens=80_000,
        max_total_tokens=160_000,
    )
