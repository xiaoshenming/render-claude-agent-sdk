from __future__ import annotations

from pathlib import Path

from scripts.run_load_test import run_fake_load


def test_one_hundred_concurrent_fake_jobs_complete_once(tmp_path: Path) -> None:
    report = run_fake_load(
        tmp_path / "load.sqlite3",
        jobs=100,
        workers=10,
    )

    assert report.submitted == 100
    assert report.completed == 100
    assert report.dead_letter == 0
    assert report.duplicate_completions == 0
    assert report.handler_calls == 100
    assert report.duration_ms > 0
