"""Small IO helpers for api.repair orchestration."""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path
from typing import Any

from .contract.build_workdir import _audit_layout_context_for_agent
from .core_candidate_view import CORE_CANDIDATE, PRELUDE, editable_candidate_path
from .interfaces import ToolBox
from .schemas import CheckResult, PROFILE_LAYOUT, REPAIRABILITY_UNKNOWN, read_json
from .statuses import REPAIR_UNCHANGED, REPAIR_WORSE


def safe_check(toolbox: ToolBox, code_path: Path, workdir: Path) -> CheckResult:
    try:
        return toolbox.checker.run_check(code_path, workdir)
    except Exception as exc:  # noqa: BLE001 - injected checker boundary
        return CheckResult.failure(f"checker_exception:{exc}")


def base_manifest(bundle: Any, workdir: Path, before: CheckResult) -> dict[str, Any]:
    return {
        "job_id": bundle.job_id,
        "profile": bundle.profile,
        "code_path": str(bundle.code_path),
        "workdir": str(workdir),
        "before": before.to_dict(),
        "contract": {"ok": None, "reasons": []},
        "repairability": {"classification": REPAIRABILITY_UNKNOWN, "reasons": []},
    }


def external_status(status: str) -> str:
    if status == REPAIR_WORSE:
        return REPAIR_UNCHANGED
    return status


def logic_contract(workdir: Path) -> dict[str, Any] | None:
    return read_optional_json(workdir / "facts" / "logic_contract.json")


def safe_area(workdir: Path) -> dict[str, Any] | None:
    return read_optional_json(workdir / "facts" / "safe_area.json")


def protected(workdir: Path) -> dict[str, Any] | None:
    return read_optional_json(workdir / "facts" / "protected.json")


def read_optional_json(path: Path) -> dict[str, Any] | None:
    try:
        data = read_json(path)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def prompt_for(profile: str, workdir: Path, *, round_no: int = 1) -> str:
    if profile == PROFILE_LAYOUT:
        return _layout_direct_prompt(workdir, round_no=round_no)
    prompt_path = Path(__file__).parent / "agent" / "prompts" / f"{profile}.md"
    base = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    ticket_path = workdir / "TICKET.md"
    ticket = ticket_path.read_text(encoding="utf-8") if ticket_path.exists() else ""
    return f"{base}\n\n{ticket}".strip()


def _layout_direct_prompt(workdir: Path, *, round_no: int) -> str:
    blocking_count = _collision_count(workdir / "layout_context.json")
    scene = _scene_name(workdir / "candidate.py")
    editable_file = editable_candidate_path(workdir)
    uses_core = editable_file == CORE_CANDIDATE
    issue_path = str((workdir / "layout_issue_digest.json").resolve())
    editable_path = str((workdir / editable_file).resolve())
    candidate_path = str((workdir / "candidate.py").resolve())
    prelude_path = str((workdir / PRELUDE).resolve())
    read_source_step = f"2. Read {editable_path} once.\n"
    edit_source_step = (
        f"3. If the issues show real source-fixable overlap, edit only {editable_path} for the clearly source-fixable layout clusters.\n"
        if uses_core
        else f"3. If the issues show real source-fixable overlap, edit {editable_path} for the clearly source-fixable layout clusters.\n"
    )
    read_constraint = (
        f"- Do not read any file except {issue_path} and {editable_path}.\n"
        if not uses_core
        else f"- Do not read any file except {issue_path} and {editable_path}.\n"
        f"- Edit only {editable_path}.\n"
        f"- Do not read candidate.py or {PRELUDE}; The full candidate.py will be composed and checked automatically.\n"
        f"- Do not read {candidate_path} or {prelude_path}.\n"
        "- Do not use /workspace paths.\n"
    )
    final_file = editable_path
    files_block = (
        f"- {issue_path}: all blocking layout collision issues.\n"
        f"- {editable_path}: the only file you may edit.\n"
    )
    if uses_core:
        files_block += f"- {candidate_path}: generated full file for checker/render; do not read or edit it.\n"
    return (
        "You are a Manim layout repair agent.\n\n"
        "Files:\n"
        f"{files_block}\n"
        "Scene:\n"
        f"- {scene}\n\n"
        "Round:\n"
        f"- {round_no}\n\n"
        "Current blocking overlap count:\n"
        f"- {blocking_count}\n\n"
        "Required protocol:\n"
        f"1. Read {issue_path} first.\n"
        f"{read_source_step}"
        f"{edit_source_step}"
        "4. Use short exact Edit.old_string snippets. If an Edit fails because source text changed, reread the editable file once and retry with a smaller exact snippet.\n"
        "5. Use multiple Edit calls only when they are clearly needed for source-fixable layout issues; after a strong improvement, stop and let the checker decide whether another round is needed.\n"
        f"6. If the issues are not safely source-fixable, leave {editable_path} unchanged.\n\n"
        "Constraints:\n"
        f"{read_constraint}"
        f"- If issue_count is nonzero and {editable_path} contains related panel/text/formula layout code, attempt a safe layout edit.\n"
        "- Do not return a generic no_fix reason; no_fix must name the specific source reason.\n"
        "- If a repeated Read is denied, use the latest source context already read; do not return no_fix because of read budget.\n"
        "- Preserve MathTex/Text strings, voiceover text, mathematical meaning, colors, animations, and teaching order.\n"
        "- Do not delete teaching content just to reduce overlap.\n"
        "- Do not write analysis, markdown, code fences, or prose.\n"
        "- Do not chase low-confidence or risk-only residual issues after a substantial improvement.\n"
        "- Return compact JSON only when the repair pass is complete.\n\n"
        "Final JSON shape:\n"
        f'{{"action":"fix","reason":"specific patch summary","file":"{final_file}"}}\n'
        '{"action":"no_fix","reason":"specific source reason"}'
    ).strip()


def _collision_count(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        for key in ("blocking_layout_issue_count", "blocking_count", "blocking"):
            value = data.get(key)
            if value is not None and not isinstance(value, bool):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
        issues = data.get("top_blocking_issues")
        return len(issues) if isinstance(issues, list) else 0
    return 0


def _available_evidence_files(workdir: Path) -> str:
    root = workdir / "evidence_queries"
    if not root.exists():
        return "- (none)"
    files = sorted(path.relative_to(workdir).as_posix() for path in root.glob("round_*/*") if path.is_file())
    if not files:
        return "- (none)"
    return "\n".join(f"- {path}" for path in files[-12:])


def refresh_layout_context_from_check(workdir: Path, check: CheckResult) -> None:
    context_path = workdir / "layout_context.json"
    if not context_path.exists():
        return
    layout_ctx = {
        "blocking_layout_issue_count": check.blocking_count,
        "pass": check.passed,
        "status": "pass" if check.passed or check.blocking_count == 0 else "layout_failed",
        "collisions": list(check.issues),
    }
    write_payload = _audit_layout_context_for_agent(layout_ctx)
    context_path.write_text(json.dumps(write_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    try:
        from tools.quality_repair_checkers.layout_repair_brief import (
            build_layout_repair_brief,
            build_layout_repair_contract,
        )

        brief = build_layout_repair_brief(write_payload)
        contract = build_layout_repair_contract(brief)
    except Exception:
        return
    (workdir / "layout_repair_brief.json").write_text(json.dumps(brief, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (workdir / "layout_repair_contract.json").write_text(json.dumps(contract, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    try:
        from tools.quality_repair_checkers.layout_repair_brief import build_layout_issue_digest

        digest = build_layout_issue_digest(write_payload)
    except Exception:
        digest = None
    if digest is not None:
        (workdir / "layout_issue_digest.json").write_text(
            json.dumps(digest, ensure_ascii=False, separators=(",", ":"), default=str),
            encoding="utf-8",
        )

def _scene_name(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return "unknown"
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    for node in classes:
        if node.name.startswith("Scene_"):
            return node.name
    for node in classes:
        if any(isinstance(item, ast.FunctionDef) and item.name == "construct" for item in node.body):
            return node.name
    return classes[0].name if classes else "unknown"


def copy_tool_config(src_dir: Path, workdir: Path) -> None:
    source = src_dir / "tool_config.json"
    if source.exists():
        shutil.copy2(source, workdir / "tool_config.json")
