from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkloadItem:
    task_id: str
    domain: str
    difficulty: str
    prompt_id: int
    knowledge_point: str
    problem: str
    expected_solution: str


@dataclass(frozen=True, slots=True)
class WorkloadSlot:
    slot_id: str
    round_id: int
    task: WorkloadItem
