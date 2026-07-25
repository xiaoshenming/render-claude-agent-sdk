"""Idempotent orchestration-run records for the SQLite adapter."""

import json
import sqlite3

from manim_quality.contracts import QualityResult
from manim_quality.revisions.store import DuplicateRunConflict, require_evidence_hash

from ._sqlite import transaction
from .validation import require_text


class SQLiteRunRecordsMixin:
    _connection: sqlite3.Connection

    def begin_run(self, job_id: str, run_id: str, request_hash: str) -> None:
        require_text(job_id, "job_id")
        require_text(run_id, "run_id")
        require_evidence_hash(request_hash)
        with transaction(self._connection):
            self._require_job(job_id)
            row = self._run_row(job_id, run_id)
            if row is not None:
                if row["request_hash"] != request_hash:
                    raise DuplicateRunConflict(f"run {run_id} has a different payload")
                return
            self._connection.execute(
                "INSERT INTO quality_runs "
                "(job_id, run_id, request_hash) VALUES (?, ?, ?)",
                (job_id, run_id, request_hash),
            )

    def get_run_result(
        self, job_id: str, run_id: str, request_hash: str
    ) -> QualityResult | None:
        row = self._run_row(job_id, run_id)
        if row is None:
            return None
        if row["request_hash"] != request_hash:
            raise DuplicateRunConflict(f"run {run_id} has a different payload")
        payload = row["result_payload"]
        return None if payload is None else QualityResult.from_dict(json.loads(payload))

    def save_run_result(
        self, job_id: str, run_id: str, request_hash: str, result: QualityResult
    ) -> None:
        payload = result_payload(result)
        with transaction(self._connection):
            row = self._require_run(job_id, run_id, request_hash)
            if row["result_payload"] is not None:
                if row["result_payload"] != payload:
                    raise DuplicateRunConflict(f"run {run_id} has a different result")
                return
            self._connection.execute(
                "UPDATE quality_runs SET result_payload = ? "
                "WHERE job_id = ? AND run_id = ?",
                (payload, job_id, run_id),
            )

    def _run_row(self, job_id: str, run_id: str) -> sqlite3.Row | None:
        return self._connection.execute(
            "SELECT * FROM quality_runs WHERE job_id = ? AND run_id = ?",
            (job_id, run_id),
        ).fetchone()

    def _require_run(self, job_id: str, run_id: str, request_hash: str) -> sqlite3.Row:
        row = self._run_row(job_id, run_id)
        if row is None or row["request_hash"] != request_hash:
            raise DuplicateRunConflict(f"run {run_id} is missing or conflicts")
        return row


def result_payload(result: QualityResult) -> str:
    return json.dumps(result.to_dict(), sort_keys=True, separators=(",", ":"))
