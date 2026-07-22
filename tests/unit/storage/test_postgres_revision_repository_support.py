from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from psycopg import OperationalError

from manim_quality.contracts import DeliveryDecision, QualityResult, QualityState
from manim_quality.revisions.fence import CommitFence
from manim_quality.revisions.store import (
    CommitFenceRejected,
    DuplicateRunConflict,
    RepositoryTransactionError,
    RevisionRepository,
    StaleWrite,
    TransitionEvidence,
)
from manim_quality.storage.factory import create_storage_factories
from manim_quality.storage.postgres import PostgresRevisionRepository
from tests.e2e.test_quality_happy_path import baseline, digest
from tests.unit.storage.postgres_fakes import Connection, Cursor



def job_row(*, version: int = 0, state: str = "BASELINE_READY"):
    return {
        "job_id": "job-1",
        "version": version,
        "state": state,
        "render_baseline_revision_id": "baseline",
        "logic_certified_revision_id": "baseline",
        "layout_certified_revision_id": "baseline",
        "delivery_revision_id": None,
        "render_baseline_evidence_hash": digest("manifest:baseline"),
        "logic_certified_evidence_hash": digest("logic"),
        "layout_certified_evidence_hash": digest("layout"),
        "delivery_evidence_hash": None,
    }


def fence() -> CommitFence:
    return CommitFence("run-1", "worker-a", "token-a", datetime(2030, 1, 1, tzinfo=UTC))


def result(decision: DeliveryDecision) -> QualityResult:
    accepted = decision in {
        DeliveryDecision.ACCEPT,
        DeliveryDecision.ACCEPT_WITH_WARNING,
    }
    return QualityResult(
        "job-1",
        decision,
        "baseline" if accepted else None,
        "artifact://code" if accepted else None,
        "artifact://render" if accepted else None,
        "artifact://certificate",
        (),
        {},
        {},
    )


def terminal_responder(target: QualityState):
    jobs = [job_row(version=3, state="FINAL_CONSISTENCY_GATE")]
    jobs.append(job_row(version=4, state=target.value))

    def respond(sql, parameters):
        if "FROM quality_queue" in sql:
            return Cursor(({"stage_run_id": "run-1"},))
        if "FROM quality_state_transitions" in sql:
            return Cursor()
        if "FROM quality_jobs" in sql:
            return Cursor((jobs.pop(0),))
        if "FROM quality_revisions" in sql:
            row = {
                "job_id": "job-1",
                "parent_revision_id": None,
                "payload": baseline().to_dict(),
            }
            return Cursor((row,))
        if "FROM quality_runs" in sql:
            row = {"request_hash": digest("request"), "result_payload": None}
            return Cursor((row,))
        if "FROM quality_evidence" in sql:
            return Cursor()
        return Cursor()

    return respond


def finalize_delivery(repository: PostgresRevisionRepository):
    evidence = TransitionEvidence("run-1", "accepted", digest("certificate"))
    return repository.finalize_delivery(
        "job-1",
        "baseline",
        QualityState.ACCEPTED,
        evidence,
        b"certificate",
        result(DeliveryDecision.ACCEPT),
        run_id="run-1",
        request_hash=digest("request"),
        expected_version=3,
        commit_fence=fence(),
    )
