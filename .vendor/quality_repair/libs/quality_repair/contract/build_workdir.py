"""Assemble quality_repair agent workdirs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..schemas import PROFILE_LOGIC, SCHEMA_VERSION, read_json, write_json
from ..core_candidate_view import build_core_candidate_view
from ..semantic_contract import GeneratedLogicContract, generate_logic_contract
from .workdir_files import (
    DEFAULT_SAFE_AREA,
    PROTECTED_DEFAULT,
    _copy_frames,
    _copy_optional_file,
    _extract_collisions,
    _extract_safe_area,
    _write_facts,
    _write_json_value,
    _write_protected,
)
from .workdir_format import _compact_issue, _compact_object, _format_issue, _format_object_ref, _object_ref
from .workdir_layout import (
    _active_visible_objects,
    _audit_layout_context_for_agent,
    _audit_summary,
    _blocking_count,
    _compact_layout_context_for_agent,
    _find_safe_area,
    _format_object_for_summary,
    _issue_object_refs,
    _layout_object_index,
)
from .workdir_normalize import (
    COLLISION_KEYS as _COLLISION_KEYS,
    FACT_OBJECT_KEYS as _FACT_OBJECT_KEYS,
    LOGIC_ISSUE_KEYS as _LOGIC_ISSUE_KEYS,
    _find_list_field,
    _normalize_layout_context,
    _normalize_logic_contract,
    _set_if_missing,
)
from .workdir_ticket import _write_ticket

if TYPE_CHECKING:
    from ..api import RepairBundle


def build_workdir(bundle: "RepairBundle", dest: Path) -> Path:
    """Build an agent workdir from a repair bundle."""
    dest.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    is_logic = bundle.profile == PROFILE_LOGIC

    _copy_candidate(bundle.code_path, dest, warnings)
    generated_logic = _generate_logic_contract(bundle, warnings) if is_logic and bundle.logic_contract is None else None
    _append_missing_input_warnings(bundle, is_logic, generated_logic, warnings)

    layout_ctx = _normalize_layout_context(_load_optional_json(bundle.layout_context, "layout_context", warnings))
    logic_contract = _normalize_logic_contract(
        _load_optional_json(bundle.logic_contract, "logic_contract", warnings)
        if generated_logic is None
        else generated_logic.logic_contract
    )
    if is_logic:
        _write_logic_workdir(dest, bundle, layout_ctx, logic_contract, warnings, generated_logic)
    elif layout_ctx is not None:
        write_json(dest / "layout_context.json", _audit_layout_context_for_agent(layout_ctx))
        write_json(dest / "facts" / "layout_context.json", layout_ctx)
        write_json(dest / "facts" / "layout_context.full.json", layout_ctx)
        if bundle.candidate_mode == "core":
            core_view = build_core_candidate_view(dest)
            if not core_view.enabled:
                warnings.append(f"core_candidate_view_disabled:{core_view.reason or 'unknown'}")
        elif bundle.candidate_mode == "full":
            warnings.append("core_candidate_view_disabled:public_full_candidate_mode")
        else:
            raise ValueError(f"unsupported_candidate_mode:{bundle.candidate_mode}")
        _write_layout_repair_brief(dest, bundle, layout_ctx, warnings)
        _write_protected(dest)

    if warnings:
        write_json(dest / "build_warnings.json", {"schema_version": SCHEMA_VERSION, "warnings": warnings})
    return dest


def _write_logic_workdir(
    dest: Path,
    bundle: "RepairBundle",
    layout_ctx: dict[str, Any] | None,
    logic_contract: dict[str, Any] | None,
    warnings: list[str],
    generated_logic: GeneratedLogicContract | None,
) -> None:
    _write_facts(dest, bundle, None, logic_contract, warnings, generated_logic=generated_logic)
    _extract_safe_area(dest, layout_ctx)
    _extract_collisions(dest, layout_ctx)
    _write_protected(dest, protect_string_literals=False)
    _write_ticket(dest, bundle, layout_ctx, logic_contract)
    _copy_frames(bundle.frames, dest, warnings)


def _append_missing_input_warnings(
    bundle: "RepairBundle",
    is_logic: bool,
    generated_logic: GeneratedLogicContract | None,
    warnings: list[str],
) -> None:
    if bundle.layout_context is None and not is_logic:
        warnings.append("layout_context_not_provided")
    if bundle.logic_contract is None and is_logic and generated_logic is None:
        warnings.append("logic_contract_not_provided")
    if bundle.source_region is None and is_logic and generated_logic is None:
        warnings.append("source_region_not_provided")


def _generate_logic_contract(bundle: "RepairBundle", warnings: list[str]) -> GeneratedLogicContract | None:
    try:
        result = generate_logic_contract(bundle.code_path)
    except Exception as exc:  # noqa: BLE001 - deterministic generator is fail-open at bundle boundary
        warnings.append(f"logic_contract_auto_generation_failed:{exc}")
        return None
    warnings.append("logic_contract_auto_generated")
    return result


def _write_layout_repair_brief(
    dest: Path,
    bundle: "RepairBundle",
    layout_ctx: dict[str, Any],
    warnings: list[str],
) -> None:
    try:
        from tools.quality_repair_checkers.layout_repair_brief import (
            build_layout_repair_brief,
            build_layout_repair_contract,
        )

        brief = build_layout_repair_brief(layout_ctx, case_id=bundle.job_id, source_path=bundle.layout_context)
        contract = build_layout_repair_contract(brief)
    except Exception as exc:  # noqa: BLE001 - repair input compression must be fail-open
        warnings.append(f"layout_repair_brief_generation_failed:{exc}")
        return
    write_json(dest / "layout_repair_brief.json", brief)
    write_json(dest / "layout_repair_contract.json", contract)
    try:
        from tools.quality_repair_checkers.layout_repair_brief import build_layout_issue_digest

        _write_compact_json(dest / "layout_issue_digest.json", build_layout_issue_digest(layout_ctx, case_id=bundle.job_id, source_path=bundle.layout_context))
    except Exception as exc:  # noqa: BLE001 - new exploratory inputs must not break legacy repair inputs
        warnings.append(f"layout_issue_digest_generation_failed:{exc}")


def _copy_candidate(code_path: Path, dest: Path, warnings: list[str]) -> None:
    target = dest / "candidate.py"
    try:
        shutil.copy2(code_path, target)
    except OSError as exc:
        warnings.append(f"candidate_copy_failed:{code_path}:{exc}")
        target.write_text("", encoding="utf-8")


def _write_compact_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")


def _load_optional_json(path: Path | None, label: str, warnings: list[str]) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        data = read_json(path)
    except (OSError, ValueError) as exc:
        warnings.append(f"{label}_unreadable:{path}:{exc}")
        return None
    if not isinstance(data, dict):
        warnings.append(f"{label}_not_object:{path}")
        return None
    return data
