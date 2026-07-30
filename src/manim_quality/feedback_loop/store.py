from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from .models import AssuranceOutcome, Candidate, LoopState, PassRecord


class JsonLoopStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> LoopState | None:
        if not self.path.is_file():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        state = payload.get("state")
        if payload.get("checksum") != _checksum(state):
            raise ValueError("feedback loop state checksum mismatch")
        return _decode(state)

    def save(self, state: LoopState) -> None:
        value = asdict(state)
        payload = {"schema_version": "feedback-loop-v1", "state": value}
        payload["checksum"] = _checksum(value)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", dir=self.path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _checksum(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decode(value: dict) -> LoopState:
    records = tuple(
        PassRecord(
            assurance_pass=row["assurance_pass"],
            candidate=Candidate(**row["candidate"]),
            outcome=AssuranceOutcome(
                grade=row["outcome"]["grade"],
                status=row["outcome"]["status"],
                issues=tuple(row["outcome"].get("issues", ())),
                usage=row["outcome"].get("usage", {}),
            ),
        )
        for row in value.get("records", ())
    )
    return LoopState(
        initial_candidate=Candidate(**value["initial_candidate"]),
        current_candidate=Candidate(**value["current_candidate"]),
        best_candidate=Candidate(**value["best_candidate"]),
        best_grade=value.get("best_grade"),
        assurance_passes=value.get("assurance_passes", 0),
        repair_rounds=value.get("repair_rounds", 0),
        records=records,
        pending_issues=tuple(value.get("pending_issues", ())),
        terminal_reason=value.get("terminal_reason"),
    )
