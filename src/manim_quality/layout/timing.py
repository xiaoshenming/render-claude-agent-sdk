"""Non-blocking timing evidence for layout checker calls."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


class TimedChecker:
    def __init__(self, checker: Any) -> None:
        self._checker = checker
        self.calls: list[dict[str, object]] = []

    def run_check(self, code_path: Path, workdir: Path) -> Any:
        started = time.perf_counter()
        try:
            result = self._checker.run_check(code_path, workdir)
        except Exception as error:
            self._record(started, error=type(error).__name__)
            raise
        self._record(
            started,
            ok=getattr(result, "ok", None),
            passed=getattr(result, "passed", None),
            blocking_count=getattr(result, "blocking_count", None),
            error=getattr(result, "error", None),
        )
        return result

    def summary(self, total_elapsed_ms: int) -> dict[str, object]:
        checker_ms = sum(int(call["elapsed_ms"]) for call in self.calls)
        return {
            "repair_total_elapsed_ms": total_elapsed_ms,
            "checker_recheck_elapsed_ms": checker_ms,
            "agent_orchestration_estimated_ms": max(0, total_elapsed_ms - checker_ms),
            "checker_calls": list(self.calls),
        }

    def _record(self, started: float, **evidence: object) -> None:
        self.calls.append(
            {
                "index": len(self.calls) + 1,
                "elapsed_ms": round((time.perf_counter() - started) * 1_000),
                **evidence,
            }
        )
