"""quality_repair.api — 对外唯一入口。

repair() 永不抛异常、永不阻断：任何内部失败（SDK 崩溃、合同断言失败、
超预算、验收环节自身失败）都返回 REPAIR_UNCHANGED / REVIEW_ERROR + 证据。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .acceptance import judge
from .agent.controller import LoopResult, run_repair_loop
from .agent.runner import ClaudeSDKRunner
from .api_types import RepairBundle, RepairResult
from .contract import assert_contract, build_workdir
from .evidence import (
    evidence_dir_for,
    write_rounds,
)
from .interfaces import ToolBox
from .pipeline_io import (
    base_manifest,
    copy_tool_config,
    logic_contract,
    prompt_for,
    protected,
    refresh_layout_context_from_check,
    safe_area,
    safe_check,
)
from .pipeline_result import early_finish, finish, finish_after_loop
from .route import classify
from .schemas import (
    AcceptanceReport,
    REPAIRABILITY_AUTO_READY,
    REPAIRABILITY_UNKNOWN,
    PROFILE_LAYOUT,
    budget_for,
    read_json,
)
from .statuses import (
    REPAIR_UNCHANGED,
    REVIEW_ERROR,
)


def repair(bundle: RepairBundle, toolbox: ToolBox) -> RepairResult:
    """编排完整修复链路。任何异常都转结构化结果，绝不上抛。"""
    evidence_dir = evidence_dir_for(
        code_path=bundle.code_path,
        job_id=bundle.job_id,
        evidence_root=bundle.evidence_root,
    )
    try:
        return _repair_impl(bundle, toolbox, evidence_dir)
    except Exception as exc:  # noqa: BLE001 - public fail-open boundary
        reason = f"repair_exception:{exc}"
        report = AcceptanceReport(status=REVIEW_ERROR, reasons=[reason])
        return finish(
            bundle=bundle,
            evidence_dir=evidence_dir,
            status=REVIEW_ERROR,
            code_path=bundle.code_path,
            repairability=REPAIRABILITY_UNKNOWN,
            before={},
            after={},
            rounds_used=0,
            tokens_used=0,
            reasons=[reason],
            acceptance=report,
            manifest={"error": reason},
        )


def _repair_impl(bundle: RepairBundle, toolbox: ToolBox, evidence_dir: Path) -> RepairResult:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    workdir = build_workdir(bundle, evidence_dir / "workdir")
    copy_tool_config(bundle.code_path.parent, workdir)
    candidate = workdir / "candidate.py"
    input_code = candidate.read_text(encoding="utf-8")
    before = safe_check(toolbox, candidate, workdir)
    if bundle.profile == PROFILE_LAYOUT and before.ok:
        refresh_layout_context_from_check(workdir, before)
    manifest: dict[str, Any] = base_manifest(bundle, workdir, before)
    if not before.ok:
        return early_finish(
            bundle=bundle,
            evidence_dir=evidence_dir,
            workdir=workdir,
            status=REVIEW_ERROR,
            repairability=REPAIRABILITY_UNKNOWN,
            before=before,
            reasons=[f"initial_check_error:{before.error or 'checker_not_ok'}"],
            manifest=manifest,
        )
    if before.passed or before.blocking_count == 0:
        decision = classify(bundle.profile, logic_contract(workdir), safe_area(workdir))
        manifest["repairability"] = decision.to_dict()
        return early_finish(
            bundle=bundle,
            evidence_dir=evidence_dir,
            workdir=workdir,
            status=REPAIR_UNCHANGED,
            repairability=decision.classification,
            before=before,
            reasons=["already_clean"],
            manifest=manifest,
        )

    decision = classify(bundle.profile, logic_contract(workdir), safe_area(workdir))
    manifest["repairability"] = decision.to_dict()
    if bundle.profile == PROFILE_LAYOUT:
        actionability = _layout_actionability(workdir)
        manifest["layout_actionability"] = actionability
        manifest["layout_actionability"]["controller_policy"] = "hint_only_agent_decides"
    if decision.classification != REPAIRABILITY_AUTO_READY:
        return early_finish(
            bundle=bundle,
            evidence_dir=evidence_dir,
            workdir=workdir,
            status=REPAIR_UNCHANGED,
            repairability=decision.classification,
            before=before,
            reasons=list(decision.reasons),
            manifest=manifest,
        )

    budget = bundle.budget or budget_for(bundle.profile, before.blocking_count)
    manifest["budget"] = budget.to_dict()
    initial_check = before
    if bundle.profile == PROFILE_LAYOUT:
        _record_deterministic_layout_prepatch_disabled(manifest, before)

    contract_ok, contract_reasons = assert_contract(workdir, initial_check, profile=bundle.profile)
    contract_warnings: list[str] = []
    if not contract_ok and _can_degrade_layout_stale_contract(
        profile=bundle.profile,
        reasons=contract_reasons,
        workdir=workdir,
    ):
        contract_warnings = list(contract_reasons)
        contract_ok = True
        contract_reasons = ["stale_object_references"]
    manifest["contract"] = {
        "ok": contract_ok,
        "reasons": list(contract_reasons),
        "warnings": list(contract_warnings),
    }
    if not contract_ok:
        return early_finish(
            bundle=bundle,
            evidence_dir=evidence_dir,
            workdir=workdir,
            status=REPAIR_UNCHANGED,
            repairability=REPAIRABILITY_UNKNOWN,
            before=initial_check,
            reasons=list(contract_reasons),
            manifest=manifest,
        )

    loop = run_repair_loop(
        workdir=workdir,
        prompt=lambda current_workdir, round_no: prompt_for(bundle.profile, current_workdir, round_no=round_no),
        runner=ClaudeSDKRunner(protected=protected(workdir)),
        checker=toolbox.checker,
        budget=budget,
        initial_check=initial_check,
        after_check=refresh_layout_context_from_check if bundle.profile == "layout" else None,
    )
    write_rounds(evidence_dir, rounds=loop.rounds, input_code=input_code, final_code=loop.final_code)
    acceptance = judge(
        workdir=workdir,
        input_code=input_code,
        output_code=loop.final_code,
        before=before,
        checker=toolbox.checker,
        renderer=toolbox.renderer,
        protected=protected(workdir),
        safe_area=safe_area(workdir),
        scene_names=[],
    )
    for reason in contract_reasons:
        if reason == "stale_object_references" and reason not in acceptance.reasons:
            acceptance.reasons.append(reason)
    return finish_after_loop(
        bundle=bundle,
        evidence_dir=evidence_dir,
        workdir=workdir,
        decision=decision,
        before=before,
        loop=loop,
        acceptance=acceptance,
        manifest=manifest,
    )


def _layout_actionability(workdir: Path) -> dict[str, Any]:
    path = workdir / "layout_repair_brief.json"
    if not path.exists():
        return {"sdk_actionable_blocking_count": None, "reason": "layout_repair_brief_missing"}
    try:
        brief = read_json(path)
    except Exception as exc:  # noqa: BLE001 - actionability must fail open
        return {"sdk_actionable_blocking_count": None, "reason": f"layout_repair_brief_unreadable:{exc}"}
    value = brief.get("sdk_actionable_blocking_count", brief.get("blocking_count"))
    try:
        sdk_actionable = int(value)
    except (TypeError, ValueError):
        sdk_actionable = None
    return {
        "raw_blocking_count": brief.get("raw_blocking_count", brief.get("blocking_count")),
        "sdk_actionable_blocking_count": sdk_actionable,
        "ignored_issue_count": brief.get("ignored_issue_count", 0),
        "hidden_issue_count": brief.get("hidden_issue_count", 0),
        "primary_failure_type": (brief.get("summary") or {}).get("primary_failure_type")
        if isinstance(brief.get("summary"), dict)
        else None,
    }


def _can_degrade_layout_stale_contract(*, profile: str, reasons: list[str], workdir: Path) -> bool:
    if profile != PROFILE_LAYOUT:
        return False
    if not reasons or not all(str(reason).startswith("missing_object:") for reason in reasons):
        return False
    actionability = _layout_actionability(workdir)
    value = actionability.get("sdk_actionable_blocking_count")
    try:
        if int(value) > 0:
            return True
    except (TypeError, ValueError):
        pass
    raw = actionability.get("raw_blocking_count")
    try:
        return int(raw) > 0
    except (TypeError, ValueError):
        return False


def _record_deterministic_layout_prepatch_disabled(manifest: dict[str, Any], before: CheckResult) -> None:
    manifest["deterministic_layout_prepatch"] = {
        "enabled": False,
        "changed": False,
        "patch_names": [],
        "reasons": ["disabled_agent_only_mode"],
        "before_blocking": before.blocking_count,
        "after_blocking": before.blocking_count,
        "accepted": False,
        "attempts": [],
    }
