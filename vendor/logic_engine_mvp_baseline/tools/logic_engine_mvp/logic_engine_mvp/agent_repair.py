from __future__ import annotations

import asyncio
import inspect
import json
import shutil
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

from .sdk_agent_runner import ClaudeSdkRepairConfig, run_sdk_repair, write_agent_result
from .settings import LlmConfig
from .validator import validate_contract


SdkRunner = Callable[..., Awaitable[dict[str, Any]] | dict[str, Any]]
REPAIR_MODES = {"hybrid", "sdk_only", "direct_patch_only"}


def build_repair_prompt(case_dir: Path) -> str:
    case_dir = Path(case_dir)
    return "\n".join(
        [
            "You are repairing one rendered Manim logic sample.",
            "",
            "Workspace:",
            f"- Current directory: {case_dir}",
            "- Read repair_contract.json first.",
            "- Read only the candidate.py source lines needed for the contract before editing.",
            "- Do not attempt Edit on candidate.py before reading candidate.py; the SDK Edit tool requires a prior Read.",
            "- Edit only candidate.py.",
            "- Do not edit before_candidate.py or any metadata/log file.",
            "",
            "Allowed SDK tools: Read, Edit.",
            "Disallowed SDK tools: Bash, Write.",
            "",
            "Rules:",
            "- Fix the general logic error described by the contract.",
            "- Contracts with validation_level=soft_llm are LLM-suggested, not deterministically verified; make only the minimal targeted edit described there.",
            "- When a contract validator contains a line number, edit only that exact source line.",
            "- If the same wrong_text appears elsewhere but is not listed in source_lines, leave it unchanged.",
            "- If a contract has replace_scope=all_matching_code_lines, use Edit with replace_all=true for that exact wrong_text.",
            "- If Edit reports multiple matches, retry with replace_all=true when the contract source_lines list has multiple entries.",
            "- Never use replace_all for a contract whose replace_scope is single_code_line.",
            "- Apply all contract edits before stopping; use one Edit call for a nearby block when that is simpler.",
            "- Do not Read candidate.py after successful Edit calls; outer validation will verify the file.",
            "- Do not repair layout overlap here.",
            "- Do not add case-specific branches keyed by sample name, file name, or object name.",
            "- Do not add explanatory comments; change only the code needed to satisfy the contract.",
            "- Keep the Manim scene renderable and avoid broad rewrites unless needed.",
            "- Stop after the minimal candidate.py edit; outer validation will judge pass or fail.",
            "- After the final successful Edit, respond with exactly: DONE",
            "- Do not explain the edit after it succeeds. Do not start a new task.",
        ]
    )


def build_open_repair_prompt(case_dir: Path) -> str:
    case_dir = Path(case_dir)
    return "\n".join(
        [
            "You are repairing one rendered Manim logic sample from an open repair task.",
            "",
            "Workspace:",
            f"- Current directory: {case_dir}",
            "- Read open_repair_task.json first.",
            "- Read only the candidate.py source needed to understand and fix the listed issue.",
            "- Do not attempt Edit on candidate.py before reading candidate.py; the SDK Edit tool requires a prior Read.",
            "- Edit only candidate.py.",
            "- Do not edit before_candidate.py or any metadata/log file.",
            "",
            "Allowed SDK tools: Read, Edit.",
            "Disallowed SDK tools: Bash, Write.",
            "",
            "Rules:",
            "- Treat open_repair_task.json as evidence, not as a guaranteed fix instruction.",
            "- Identify the smallest general logic correction that makes the scene mathematically coherent.",
            "- Prefer correcting wrong visible claims, formulas, numeric labels, and reasoning text over broad rewrites.",
            "- Do not repair layout overlap here.",
            "- Do not add case-specific branches keyed by sample name, file name, or object name.",
            "- Do not add explanatory comments; change only the code needed to fix the logic.",
            "- Keep the Manim scene renderable and avoid broad rewrites unless the logic cannot be fixed locally.",
            "- Stop after the minimal candidate.py edit; outer render and review will judge pass or fail.",
            "- After the final successful Edit, respond with exactly: DONE",
            "- Do not explain the edit after it succeeds. Do not start a new task.",
        ]
    )


def run_case_agent(
    case_dir: Path,
    config: LlmConfig,
    *,
    sdk_runner: SdkRunner = run_sdk_repair,
    max_turns: int = 6,
    max_budget_usd: float | None = 0.75,
    repair_mode: str = "hybrid",
) -> dict[str, Any]:
    case_dir = Path(case_dir)
    contract_path = case_dir / "repair_contract.json"
    candidate_path = case_dir / "candidate.py"
    if not contract_path.exists():
        raise FileNotFoundError(f"repair_contract.json not found: {contract_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate.py not found: {candidate_path}")
    if repair_mode not in REPAIR_MODES:
        raise ValueError(f"unknown repair_mode: {repair_mode}")

    direct_result = None if repair_mode == "sdk_only" else _try_direct_line_patch(candidate_path, contract_path)
    if direct_result is not None:
        effective_max_turns = 0
        result = direct_result
    elif repair_mode == "direct_patch_only":
        effective_max_turns = 0
        result = _direct_patch_unavailable_result(candidate_path)
    else:
        effective_max_turns = _resolve_max_turns(contract_path, max_turns=max_turns)
        sdk_config = ClaudeSdkRepairConfig(
            base_url=config.base_url,
            api_key=config.api_key,
            model=config.model,
            cwd=str(case_dir),
            max_turns=effective_max_turns,
            max_budget_usd=max_budget_usd,
        )
        result = _resolve_runner_result(sdk_runner(prompt=build_repair_prompt(case_dir), config=sdk_config))
    write_agent_result(case_dir / "agent_messages.json", result)

    after_path = case_dir / "after_candidate.py"
    shutil.copy2(candidate_path, after_path)
    validation = validate_contract(candidate_path, contract_path)
    _write_json(case_dir / "validation_after.json", validation)

    token_usage = {
        "sdk_ok": bool(result.get("ok")),
        "requested_max_turns": max_turns,
        "effective_max_turns": effective_max_turns,
        "usage": result.get("usage") or {},
        "permission_summary": result.get("permission_summary") or {},
    }
    _write_json(case_dir / "token_usage.json", token_usage)

    status = _read_status(case_dir)
    status.update(
        {
            "stage": _stage_from_result(result, validation),
            "sdk_ok": bool(result.get("ok")),
            "validation_passed": bool(validation.get("passed")),
            "requested_max_turns": max_turns,
            "effective_max_turns": effective_max_turns,
            "usage": result.get("usage") or {},
            "permission_summary": result.get("permission_summary") or {},
            "repair_mode": repair_mode,
        }
    )
    status["artifacts"].update(
        {
            "agent_messages": "ready",
            "after_candidate": "ready",
            "validation_after": "ready",
            "token_usage": "ready",
        }
    )
    _write_json(case_dir / "case_status.json", status)
    return status


def run_case_open_agent(
    case_dir: Path,
    config: LlmConfig,
    *,
    sdk_runner: SdkRunner = run_sdk_repair,
    max_turns: int = 8,
    max_budget_usd: float | None = 0.75,
) -> dict[str, Any]:
    case_dir = Path(case_dir)
    task_path = case_dir / "open_repair_task.json"
    candidate_path = case_dir / "candidate.py"
    if not task_path.exists():
        raise FileNotFoundError(f"open_repair_task.json not found: {task_path}")
    if not candidate_path.exists():
        raise FileNotFoundError(f"candidate.py not found: {candidate_path}")

    sdk_config = ClaudeSdkRepairConfig(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        cwd=str(case_dir),
        max_turns=max_turns,
        max_budget_usd=max_budget_usd,
    )
    result = dict(_resolve_runner_result(sdk_runner(prompt=build_open_repair_prompt(case_dir), config=sdk_config)))
    result["execution_mode"] = "open_sdk_agent"
    write_agent_result(case_dir / "agent_messages.json", result)

    after_path = case_dir / "after_candidate.py"
    shutil.copy2(candidate_path, after_path)
    token_usage = {
        "sdk_ok": bool(result.get("ok")),
        "requested_max_turns": max_turns,
        "effective_max_turns": max_turns,
        "usage": result.get("usage") or {},
        "permission_summary": result.get("permission_summary") or {},
        "repair_task_type": "open_repair",
    }
    _write_json(case_dir / "token_usage.json", token_usage)

    status = _read_status(case_dir)
    status.update(
        {
            "stage": _open_stage_from_result(result),
            "sdk_ok": bool(result.get("ok")),
            "open_agent_completed": bool(result.get("ok")),
            "requested_max_turns": max_turns,
            "effective_max_turns": max_turns,
            "usage": result.get("usage") or {},
            "permission_summary": result.get("permission_summary") or {},
            "repair_task_type": "open_repair",
        }
    )
    status["artifacts"].update(
        {
            "agent_messages": "ready",
            "after_candidate": "ready",
            "validation_after": "not_applicable",
            "token_usage": "ready",
        }
    )
    _write_json(case_dir / "case_status.json", status)
    return status


def _resolve_max_turns(contract_path: Path, *, max_turns: int, hard_cap: int = 10) -> int:
    base_turns = max(1, min(max_turns, hard_cap))
    try:
        contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return base_turns
    supported_count = _int(contract.get("supported_contract_count"))
    if supported_count == 0 and isinstance(contract.get("contracts"), list):
        supported_count = len(contract["contracts"])
    if supported_count >= 3:
        return hard_cap
    return base_turns


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_runner_result(value: Awaitable[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
    if inspect.isawaitable(value):
        return asyncio.run(value)
    return value


def _stage_from_result(result: dict[str, Any], validation: dict[str, Any]) -> str:
    if validation.get("passed"):
        return "validation_passed"
    if not result.get("ok"):
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        if error.get("type") == "sdk_api_unavailable":
            return "sdk_api_unavailable"
        if _is_budget_exceeded(error):
            return "budget_exceeded"
        return "agent_failed"
    if validation.get("passed"):
        return "validation_passed"
    return "validation_failed"


def _open_stage_from_result(result: dict[str, Any]) -> str:
    if result.get("ok"):
        return "open_agent_completed"
    error = result.get("error") if isinstance(result.get("error"), dict) else {}
    if error.get("type") == "sdk_api_unavailable":
        return "sdk_api_unavailable"
    if _is_budget_exceeded(error):
        return "budget_exceeded"
    return "open_agent_failed"


def _try_direct_line_patch(candidate_path: Path, contract_path: Path) -> dict[str, Any] | None:
    try:
        contract = json.loads(Path(contract_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    contracts = contract.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        return None
    replacements = [_direct_replacement(item) for item in contracts]
    if any(item is None for item in replacements):
        return None

    original = Path(candidate_path).read_text(encoding="utf-8")
    started = time.monotonic()
    lines = original.splitlines(keepends=True)
    applied = []
    for replacement in replacements:
        assert replacement is not None
        line_no = replacement["line_no"]
        if line_no < 1 or line_no > len(lines):
            Path(candidate_path).write_text(original, encoding="utf-8")
            return None
        current = lines[line_no - 1]
        newline = "\r\n" if current.endswith("\r\n") else "\n" if current.endswith("\n") else ""
        body = current[: -len(newline)] if newline else current
        if body.strip() != replacement["wrong_text"].strip():
            Path(candidate_path).write_text(original, encoding="utf-8")
            return None
        indent = body[: len(body) - len(body.lstrip())]
        lines[line_no - 1] = f"{indent}{replacement['expected_text'].strip()}{newline}"
        applied.append({"line": line_no, "kind": "single_code_line"})

    Path(candidate_path).write_text("".join(lines), encoding="utf-8")
    validation = validate_contract(candidate_path, contract_path)
    if not validation.get("passed"):
        Path(candidate_path).write_text(original, encoding="utf-8")
        return None

    return {
        "ok": True,
        "error": None,
        "elapsed_sec": round(time.monotonic() - started, 3),
        "execution_mode": "direct_line_patch",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "tool_calls": {},
            "tool_step_count": 0,
        },
        "messages": [{"type": "direct_line_patch", "applied": applied}],
        "permission_summary": {
            "cwd": str(Path(candidate_path).parent),
            "model": "deterministic",
            "base_url": "",
            "api_key": "",
            "allowed_tools": ["direct_line_patch"],
            "disallowed_tools": ["Bash", "Write", "Read", "Edit"],
            "permission_mode": "direct",
            "max_turns": 0,
            "max_budget_usd": 0.0,
        },
    }


def _direct_replacement(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    if item.get("kind") != "text_replacement":
        return None
    if item.get("validation_level") == "soft_llm":
        return None
    if item.get("replace_scope") != "single_code_line":
        return None
    source_lines = item.get("source_lines")
    if not isinstance(source_lines, list) or len(source_lines) != 1:
        return None
    wrong_text = str(item.get("wrong_text") or "").strip()
    expected_text = str(item.get("expected_text") or "").strip()
    if not wrong_text or not expected_text:
        return None
    try:
        line_no = int(source_lines[0])
    except (TypeError, ValueError):
        return None
    return {"line_no": line_no, "wrong_text": wrong_text, "expected_text": expected_text}


def _direct_patch_unavailable_result(candidate_path: Path) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "type": "direct_patch_unavailable",
            "message": "No safe direct line patch was available and repair_mode=direct_patch_only forbids SDK fallback.",
        },
        "elapsed_sec": 0.0,
        "execution_mode": "direct_patch_unavailable",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "tool_calls": {},
            "tool_step_count": 0,
        },
        "messages": [],
        "permission_summary": {
            "cwd": str(Path(candidate_path).parent),
            "model": "deterministic",
            "base_url": "",
            "api_key": "",
            "allowed_tools": ["direct_line_patch"],
            "disallowed_tools": ["SDK", "Bash", "Write", "Read", "Edit"],
            "permission_mode": "direct_patch_only",
            "max_turns": 0,
            "max_budget_usd": 0.0,
        },
    }


def _is_budget_exceeded(error: dict[str, Any]) -> bool:
    message = str(error.get("message") or "").lower()
    return "maximum budget" in message or "budget" in str(error.get("type") or "").lower()


def _read_status(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "case_status.json"
    if not path.exists():
        return {"artifacts": {}}
    status = json.loads(path.read_text(encoding="utf-8"))
    status.setdefault("artifacts", {})
    return status


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
