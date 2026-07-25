from pathlib import Path

import pytest

from manim_quality.contracts import QualityState
from manim_quality.revisions.store import (
    DuplicateRunConflict,
    StaleWrite,
    TransitionEvidence,
    TransitionReplayAdvanced,
)
from manim_quality.storage.database import SQLiteRevisionRepository
from tests.e2e.test_quality_happy_path import baseline, digest


def test_transition_is_persisted_and_matching_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    try:
        repository.create_job("job-1", baseline())
        evidence = TransitionEvidence("run-1:logic", "logic_started", digest("logic"))
        changed = repository.transition_state(
            "job-1",
            QualityState.BASELINE_READY,
            QualityState.LOGIC_REVIEWING,
            evidence,
            expected_version=0,
        )
        retried = repository.transition_state(
            "job-1",
            QualityState.BASELINE_READY,
            QualityState.LOGIC_REVIEWING,
            evidence,
            expected_version=0,
        )
        assert retried == changed
        assert repository.list_transitions("job-1")[0].run_id == evidence.run_id
    finally:
        repository.close()


def test_matching_transition_replay_rejects_unrelated_advanced_snapshot(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    try:
        repository.create_job("job-1", baseline())
        first = TransitionEvidence("run-1:logic", "logic_started", digest("logic"))
        snapshot = repository.transition_state(
            "job-1",
            QualityState.BASELINE_READY,
            QualityState.LOGIC_REVIEWING,
            first,
            expected_version=0,
        )
        repository.transition_state(
            "job-1",
            QualityState.LOGIC_REVIEWING,
            QualityState.HOLD,
            TransitionEvidence("run-2:hold", "hold", digest("hold")),
            expected_version=snapshot.version,
        )

        with pytest.raises(TransitionReplayAdvanced):
            repository.transition_state(
                "job-1",
                QualityState.BASELINE_READY,
                QualityState.LOGIC_REVIEWING,
                first,
                expected_version=0,
            )
    finally:
        repository.close()


def test_transition_rejects_conflicting_duplicate_and_stale_worker(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    try:
        repository.create_job("job-1", baseline())
        evidence = TransitionEvidence("run-1:logic", "logic_started", digest("logic"))
        repository.transition_state(
            "job-1",
            QualityState.BASELINE_READY,
            QualityState.LOGIC_REVIEWING,
            evidence,
            expected_version=0,
        )
        with pytest.raises(DuplicateRunConflict):
            repository.transition_state(
                "job-1",
                QualityState.BASELINE_READY,
                QualityState.LOGIC_REVIEWING,
                TransitionEvidence(evidence.run_id, "other", digest("other")),
                expected_version=0,
            )
        with pytest.raises(StaleWrite):
            repository.transition_state(
                "job-1",
                QualityState.LOGIC_REVIEWING,
                QualityState.HOLD,
                TransitionEvidence("run-1:hold", "hold", digest("hold")),
                expected_version=0,
            )
    finally:
        repository.close()
