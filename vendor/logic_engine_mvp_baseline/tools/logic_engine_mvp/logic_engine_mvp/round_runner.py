from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from .agent_repair import run_case_agent, run_case_open_agent
from .render_check import run_render_check
from .round_report import write_round_reports
from .run_manager import advance_case_from_review, run_case_reviewer
from .settings import load_agent_config, load_reviewer_config


REVIEWER_ENV = "LOGIC_REVIEWER_API_KEY"
AGENT_ENV = "LOGIC_AGENT_API_KEY"


def run_round(
    round_dir: Path,
    *,
    dry_run: bool = False,
    env: Mapping[str, str] | None = None,
    render: bool = True,
    max_turns: int = 6,
    max_budget_usd: float | None = 0.75,
    render_timeout_sec: int = 420,
    repair_mode: str = "hybrid",
    allow_soft_repair: bool = False,
    allow_open_repair: bool = False,
) -> dict[str, Any]:
    round_dir = Path(round_dir)
    values = os.environ if env is None else env
    cases = _plan_cases(round_dir, render=render)
    required_env = _required_env_for_cases(cases)
    missing_env = [name for name in required_env if not values.get(name)]
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "ready_to_execute": not missing_env,
            "round_dir": str(round_dir),
            "repair_mode": repair_mode,
            "allow_soft_repair": allow_soft_repair,
            "allow_open_repair": allow_open_repair,
            "missing_env": missing_env,
            "case_count": len(cases),
            "cases": cases,
            "executed_count": 0,
        }
    if missing_env:
        return {
            "ok": False,
            "dry_run": False,
            "ready_to_execute": False,
            "round_dir": str(round_dir),
            "repair_mode": repair_mode,
            "allow_soft_repair": allow_soft_repair,
            "allow_open_repair": allow_open_repair,
            "missing_env": missing_env,
            "case_count": len(cases),
            "cases": cases,
            "executed_count": 0,
            "error": {"type": "missing_environment", "message": "Missing required API environment variables."},
        }

    reviewer_config = load_reviewer_config(values) if REVIEWER_ENV in required_env else None
    agent_config = load_agent_config(values) if AGENT_ENV in required_env else None
    executed: list[dict[str, Any]] = []
    for item in cases:
        case_dir = Path(item["case_dir"])
        action = item["next_action"]
        if action == "review_case":
            if reviewer_config is None:
                raise RuntimeError("reviewer_config is required for review_case")
            run_case_reviewer(case_dir, reviewer_config)
            executed.append({"sample_id": item["sample_id"], "action": action})
            item = _plan_case(case_dir, render=render)
            action = item["next_action"]
        if action == "advance_case":
            advance_case_from_review(
                case_dir,
                allow_soft_repair=allow_soft_repair,
                allow_open_repair=allow_open_repair,
            )
            executed.append({"sample_id": item["sample_id"], "action": action})
            item = _plan_case(case_dir, render=render)
            action = item["next_action"]
        if action == "agent_case":
            if agent_config is None:
                raise RuntimeError("agent_config is required for agent_case")
            run_case_agent(
                case_dir,
                agent_config,
                max_turns=max_turns,
                max_budget_usd=max_budget_usd,
                repair_mode=repair_mode,
            )
            executed.append({"sample_id": item["sample_id"], "action": action})
            item = _plan_case(case_dir, render=render)
            action = item["next_action"]
        if action == "open_agent_case":
            if agent_config is None:
                raise RuntimeError("agent_config is required for open_agent_case")
            run_case_open_agent(
                case_dir,
                agent_config,
                max_turns=max_turns,
                max_budget_usd=max_budget_usd,
            )
            executed.append({"sample_id": item["sample_id"], "action": action})
            item = _plan_case(case_dir, render=render)
            action = item["next_action"]
        if action == "render_case":
            affected_only = item["stage"] != "open_agent_completed"
            result = run_render_check(case_dir, affected_only=affected_only, timeout_sec=render_timeout_sec)
            executed.append({"sample_id": item["sample_id"], "action": action, "passed": bool(result.get("passed"))})

    summary = write_round_reports(round_dir)
    return {
        "ok": True,
        "dry_run": False,
        "ready_to_execute": True,
        "round_dir": str(round_dir),
        "repair_mode": repair_mode,
        "allow_soft_repair": allow_soft_repair,
        "allow_open_repair": allow_open_repair,
        "missing_env": [],
        "case_count": len(cases),
        "executed_count": len(executed),
        "executed": executed,
        "summary": summary,
    }


def write_run_round_result(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _plan_cases(round_dir: Path, *, render: bool) -> list[dict[str, Any]]:
    cases_dir = Path(round_dir) / "cases"
    if not cases_dir.exists():
        return []
    return [_plan_case(case_dir, render=render) for case_dir in sorted(p for p in cases_dir.iterdir() if p.is_dir())]


def _plan_case(case_dir: Path, *, render: bool) -> dict[str, Any]:
    status = _read_status(case_dir)
    stage = str(status.get("stage") or "unknown")
    sample_id = str(status.get("sample_id") or case_dir.name)
    next_action = _next_action(case_dir, stage, render=render)
    return {
        "sample_id": sample_id,
        "case_dir": str(case_dir),
        "stage": stage,
        "next_action": next_action,
    }


def _next_action(case_dir: Path, stage: str, *, render: bool) -> str:
    if stage == "pending_reviewer":
        return "review_case"
    if stage == "pending_verifier":
        return "advance_case"
    if stage == "pending_agent":
        return "agent_case"
    if stage == "pending_open_agent":
        return "open_agent_case"
    if render and stage == "open_agent_completed" and not (case_dir / "render_check.json").exists():
        return "render_case"
    if render and stage == "validation_passed" and not (case_dir / "render_check.json").exists():
        return "render_case"
    return "none"


def _required_env_for_cases(cases: list[dict[str, Any]]) -> list[str]:
    needs_reviewer = False
    needs_agent = False
    for case in cases:
        stage = str(case.get("stage") or "")
        action = str(case.get("next_action") or "")
        if action == "review_case" or stage == "pending_reviewer":
            needs_reviewer = True
            needs_agent = True
        elif action in {"advance_case", "agent_case", "open_agent_case"} or stage in {
            "pending_verifier",
            "pending_agent",
            "pending_open_agent",
        }:
            needs_agent = True

    required: list[str] = []
    if needs_reviewer:
        required.append(REVIEWER_ENV)
    if needs_agent:
        required.append(AGENT_ENV)
    return required


def _read_status(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "case_status.json"
    if not path.exists():
        return {"sample_id": case_dir.name, "stage": "unknown"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"sample_id": case_dir.name, "stage": "unknown"}
    return payload if isinstance(payload, dict) else {"sample_id": case_dir.name, "stage": "unknown"}
