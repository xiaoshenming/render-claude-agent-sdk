from pathlib import Path

import pytest

from manim_quality.contracts import QualityState
from manim_quality.revisions.store import RepositoryTransactionError
from manim_quality.storage.database import SQLiteRevisionRepository
from tests.e2e.test_quality_happy_path import (
    StageAction,
    baseline,
    execution_request,
    service,
)


def test_certificate_checkpoint_and_terminal_state_rollback_together(
    tmp_path: Path,
) -> None:
    repository = SQLiteRevisionRepository(tmp_path / "quality.sqlite3")
    repository.create_job("job-1", baseline())
    repository._connection.execute(  # type: ignore[attr-defined]
        """
        CREATE TRIGGER inject_delivery_failure
        BEFORE UPDATE ON quality_jobs
        WHEN NEW.state IN ('ACCEPTED', 'ACCEPTED_WITH_WARNING')
        BEGIN
            SELECT RAISE(ABORT, 'injected delivery failure');
        END
        """
    )
    try:
        request = execution_request()
        with pytest.raises(
            RepositoryTransactionError, match="injected delivery failure"
        ):
            service(repository, StageAction.CLEAN, StageAction.CLEAN).execute(request)
        snapshot = repository.get_job("job-1")
        evidence_count = repository._connection.execute(  # type: ignore[attr-defined]
            "SELECT COUNT(*) FROM quality_evidence"
        ).fetchone()[0]

        assert snapshot.state is QualityState.FINAL_CONSISTENCY_GATE
        assert snapshot.delivery_revision_id is None
        assert snapshot.delivery_evidence_hash is None
        assert evidence_count == 0
        assert (
            repository.get_run_result(
                request.job_id, request.run_id, request.request_hash
            )
            is None
        )
        assert repository.list_rollbacks("job-1") == ()
        assert all(
            record.reason_code != "delivery_finalized"
            for record in repository.list_transitions("job-1")
        )
    finally:
        repository.close()
