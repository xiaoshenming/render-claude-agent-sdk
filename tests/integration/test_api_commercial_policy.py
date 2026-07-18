from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import ApiSettings, create_app
from manim_quality.delivery.policy import CommercialWarningPolicy, TenantLimits
from tests.integration.test_api_jobs import authenticator, headers, submission


def test_api_enforces_stricter_per_tenant_concurrency_limit(tmp_path: Path) -> None:
    policy = CommercialWarningPolicy(
        version="commercial-v1",
        warning_rules=(),
        hard_blockers=frozenset(),
        default_limits=TenantLimits(50_000, 1),
    )
    app = create_app(
        ApiSettings(
            database=tmp_path / "commercial.sqlite3",
            max_active_jobs=100,
            max_queued_jobs=100,
        ),
        authenticator=authenticator(),
        commercial_policy=policy,
    )
    with TestClient(app) as client:
        first = client.post(
            "/v1/quality/jobs",
            headers=headers("tenant-a"),
            json=submission(),
        )
        second = client.post(
            "/v1/quality/jobs",
            headers=headers("tenant-a"),
            json=submission(job_id="job-2", idempotency_key="idem-2"),
        )

    assert first.status_code == 202
    assert second.status_code == 429
