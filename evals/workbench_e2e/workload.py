from __future__ import annotations

import json
from pathlib import Path

from .models import WorkloadItem, WorkloadSlot

WORKLOAD_PATH = Path(__file__).with_name("workload_v1.json")
ROUND_SIZE = 15
ROUND_COUNT = 3


def load_workload(path: Path = WORKLOAD_PATH) -> tuple[WorkloadItem, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "manim-quality.workbench-workload.v1":
        raise ValueError("unsupported workbench workload schema")
    items = tuple(WorkloadItem(**item) for item in payload.get("items", []))
    if len(items) != 20 or len({item.task_id for item in items}) != len(items):
        raise ValueError("workbench workload must contain 20 unique items")
    return items


def round_slots(
    workload: tuple[WorkloadItem, ...], round_id: int
) -> tuple[WorkloadSlot, ...]:
    if len(workload) != 20:
        raise ValueError("round scheduling requires the frozen 20-item workload")
    if round_id not in range(1, ROUND_COUNT + 1):
        raise ValueError("round_id must be between 1 and 3")
    start = (round_id - 1) * ROUND_SIZE
    return tuple(
        WorkloadSlot(
            slot_id=f"slot-{absolute + 1:03d}",
            round_id=round_id,
            task=workload[absolute % len(workload)],
        )
        for absolute in range(start, start + ROUND_SIZE)
    )
