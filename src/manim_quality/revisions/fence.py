"""Immutable identity required for a lease-fenced quality commit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CommitFence:
    stage_run_id: str
    lease_owner: str
    lease_token: str
    deadline: datetime

    def __post_init__(self) -> None:
        for name in ("stage_run_id", "lease_owner", "lease_token"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if self.deadline.tzinfo is None:
            raise ValueError("deadline must be timezone-aware")

    @classmethod
    def from_queue_item(cls, item) -> CommitFence:
        if item.lease_owner is None or item.lease_token is None:
            raise ValueError("queue item must hold an active lease")
        return cls(
            item.stage_run_id,
            item.lease_owner,
            item.lease_token,
            item.deadline,
        )
