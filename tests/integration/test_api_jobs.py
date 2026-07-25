from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.auth import GatewayHmacAuthenticator
from apps.api.main import ApiSettings, create_app
from manim_quality.contracts import DeliveryDecision, QualityResult
from manim_quality.storage.database import SQLiteRevisionRepository
from manim_quality.storage.intake import (
    IntakeLimits,
    IntakeTransactionError,
    SQLiteIntakeRepository,
)
from tests.e2e.test_quality_happy_path import baseline

AUTH_SECRET = b"test-runtime-gateway-secret"


def authenticator() -> GatewayHmacAuthenticator:
    return GatewayHmacAuthenticator(AUTH_SECRET, max_age_seconds=300)


def submission(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "job_id": "job-1",
        "tenant_id": "tenant-a",
        "candidate_code_ref": "artifact://candidate.py",
        "problem_text": "Prove the angle equality.",
        "planning": {"scenes": ["ProofScene"]},
        "expected_answer": None,
        "render_manifest_ref": "artifact://render.json",
        "asset_manifest_ref": None,
        "callback_url": None,
        "idempotency_key": "idem-1",
    }
    payload.update(changes)
    return payload


def headers(tenant_id: str) -> dict[str, str]:
    return authenticator().headers(tenant_id)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(
        ApiSettings(database=tmp_path / "quality.sqlite3", max_request_bytes=4096),
        authenticator=authenticator(),
    )
    with TestClient(app) as test_client:
        yield test_client


def post(client: TestClient, payload: dict[str, object]):
    return client.post(
        "/v1/quality/jobs",
        headers=headers(str(payload["tenant_id"])),
        json=payload,
    )


def test_submission_is_idempotent_and_returns_current_queue_state(
    client: TestClient,
) -> None:
    first = post(client, submission())
    second = post(client, submission())

    assert first.status_code == 202
    assert first.json() == second.json()
    assert first.json() == {
        "schema_version": 1,
        "job_id": "job-1",
        "stage_run_id": first.json()["stage_run_id"],
        "queue_state": "QUEUED",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"problem_text": "different"},
        {"job_id": "job-2"},
        {"idempotency_key": "idem-2"},
    ],
)
def test_conflicting_identity_or_payload_returns_409(
    client: TestClient, change: dict[str, object]
) -> None:
    assert post(client, submission()).status_code == 202
    assert post(client, submission(**change)).status_code == 409


def test_strict_json_and_content_type(client: TestClient) -> None:
    wrong_type = client.post(
        "/v1/quality/jobs",
        headers={**headers("tenant-a"), "Content-Type": "text/plain"},
        content=b"{}",
    )
    unknown = post(client, submission(unexpected=True))

    assert wrong_type.status_code == 415
    assert unknown.status_code == 422


def test_request_size_checks_header_actual_and_dishonest_length(tmp_path: Path) -> None:
    app = create_app(
        ApiSettings(database=tmp_path / "q.sqlite3", max_request_bytes=64),
        authenticator=authenticator(),
    )
    with TestClient(app) as sized:
        actual = post(sized, submission(problem_text="x" * 100))
        header = sized.post(
            "/v1/quality/jobs",
            headers={
                **headers("tenant-a"),
                "Content-Type": "application/json",
                "Content-Length": "9999",
            },
            content=b"{}",
        )
        dishonest = sized.post(
            "/v1/quality/jobs",
            headers={
                **headers("tenant-a"),
                "Content-Type": "application/json",
                "Content-Length": "1",
            },
            content=b'{"padding":"' + b"x" * 100 + b'"}',
        )

    assert (actual.status_code, header.status_code, dishonest.status_code) == (
        413,
        413,
        413,
    )


def test_quota_check_and_insert_are_atomic(tmp_path: Path) -> None:
    app = create_app(
        ApiSettings(
            database=tmp_path / "q.sqlite3",
            max_active_jobs=1,
            max_queued_jobs=1,
        ),
        authenticator=authenticator(),
    )
    with TestClient(app) as quota_client:
        assert post(quota_client, submission()).status_code == 202
        denied = post(
            quota_client,
            submission(job_id="job-2", idempotency_key="idem-2"),
        )

    assert denied.status_code == 429


def test_tenant_scoped_reads_never_leak(client: TestClient) -> None:
    assert post(client, submission()).status_code == 202
    own = client.get("/v1/quality/jobs/job-1", headers=headers("tenant-a"))
    foreign = client.get("/v1/quality/jobs/job-1", headers=headers("tenant-b"))

    assert own.status_code == 200
    assert own.json()["queue_state"] == "QUEUED"
    assert own.json()["quality_state"] is None
    assert foreign.status_code == 404
    for suffix in ("revisions", "certificate", "evidence"):
        response = client.get(
            f"/v1/quality/jobs/job-1/{suffix}", headers=headers("tenant-b")
        )
        assert response.status_code == 404


def test_queue_publication_failure_rolls_back_submission(tmp_path: Path) -> None:
    def fail_publication() -> None:
        raise IntakeTransactionError("injected")

    app = create_app(
        ApiSettings(database=tmp_path / "q.sqlite3"),
        authenticator=authenticator(),
        publication_probe=fail_publication,
    )
    with TestClient(app, raise_server_exceptions=False) as failed:
        response = post(failed, submission())
        lookup = failed.get("/v1/quality/jobs/job-1", headers=headers("tenant-a"))

    assert response.status_code == 503
    assert lookup.status_code == 404


def test_same_tenant_idempotency_is_atomic_under_concurrency(tmp_path: Path) -> None:
    database = tmp_path / "concurrent.sqlite3"

    def submit_once():
        repository = SQLiteIntakeRepository(database)
        try:
            return repository.submit(submission(), IntakeLimits())
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: submit_once(), range(2)))

    assert receipts[0] == receipts[1]


def test_authenticated_tenant_must_match_body_and_unsigned_is_rejected(
    client: TestClient,
) -> None:
    mismatch = client.post(
        "/v1/quality/jobs", headers=headers("tenant-b"), json=submission()
    )
    unsigned = client.post(
        "/v1/quality/jobs",
        headers={"X-Tenant-Id": "tenant-a"},
        json=submission(),
    )

    assert mismatch.status_code == 403
    assert unsigned.status_code == 401


def test_app_fails_fast_without_authenticator(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="authenticator"):
        create_app(ApiSettings(database=tmp_path / "q.sqlite3"))


def test_global_job_identity_blocks_cross_tenant(client: TestClient) -> None:
    assert post(client, submission()).status_code == 202
    conflict = post(
        client,
        submission(tenant_id="tenant-b", idempotency_key="tenant-b-idem"),
    )

    assert conflict.status_code == 409


def test_job_read_exposes_quality_state_queue_state_and_result(
    tmp_path: Path,
) -> None:
    database = tmp_path / "quality.sqlite3"
    app = create_app(ApiSettings(database=database), authenticator=authenticator())
    with TestClient(app) as state_client:
        receipt = post(state_client, submission()).json()
        repository = SQLiteRevisionRepository(database)
        repository.create_job("job-1", baseline())
        request_hash = "sha256:" + "b" * 64
        repository.begin_run("job-1", receipt["stage_run_id"], request_hash)
        repository.save_run_result(
            "job-1",
            receipt["stage_run_id"],
            request_hash,
            QualityResult(
                job_id="job-1",
                decision=DeliveryDecision.HOLD,
                accepted_revision_id=None,
                final_code_ref=None,
                final_render_manifest_ref=None,
                certificate_ref=None,
                warnings=("held",),
                token_usage={},
                timings_ms={},
            ),
        )
        response = state_client.get(
            "/v1/quality/jobs/job-1", headers=headers("tenant-a")
        )

    assert response.status_code == 200
    assert response.json()["quality_state"] == "BASELINE_READY"
    assert response.json()["queue_state"] == "QUEUED"
    assert response.json()["result"]["decision"] == "HOLD"
