"""Idempotent lifecycle helpers for remote Reviewer processes."""

from ._subagent_clock import now_ms


def replace_idle_agent_id(run, agent_id: str, active_ids: set[str]) -> bool:
    if run.solution_read or run.result is not None or run.stopped_ms is not None:
        return False
    if agent_id in active_ids:
        return False
    run.agent_ids.add(agent_id)
    if run.agent_id is None:
        run.agent_id = agent_id
        run.started_ms = now_ms()
    active_ids.add(agent_id)
    return True
