from pathlib import Path
from types import SimpleNamespace

from manim_quality.layout.timing import TimedChecker


def test_timed_checker_records_non_blocking_recheck_evidence(tmp_path: Path) -> None:
    class Checker:
        def run_check(self, code_path: Path, workdir: Path):
            del code_path, workdir
            return SimpleNamespace(
                ok=True, passed=False, blocking_count=3, error=None
            )

    checker = TimedChecker(Checker())
    result = checker.run_check(tmp_path / "candidate.py", tmp_path / "evidence")
    timing = checker.summary(10)

    assert result.blocking_count == 3
    assert timing["repair_total_elapsed_ms"] == 10
    assert len(timing["checker_calls"]) == 1
    assert timing["checker_calls"][0]["blocking_count"] == 3
    assert timing["agent_orchestration_estimated_ms"] <= 10
