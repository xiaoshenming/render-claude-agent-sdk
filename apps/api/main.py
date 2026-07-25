"""FastAPI factory for service delivery; importing it has no side effects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from manim_quality.storage.factory import StorageFactories, create_storage_factories
from manim_quality.storage.queue_models import IntakeLimits

from .auth import TenantAuthenticator
from .routes.jobs import router as jobs_router
from .routes.modifications import router as modifications_router
from .routes.revisions import router as revisions_router
from .service import TenantReadService


@dataclass(frozen=True, slots=True)
class ApiSettings:
    database: str | Path | None = None
    storage_dsn: str | None = None
    max_request_bytes: int = 1_048_576
    max_active_jobs: int = 100
    max_queued_jobs: int = 100

    def __post_init__(self) -> None:
        if (self.database is None) == (self.storage_dsn is None):
            raise ValueError("exactly one of database or storage_dsn is required")

    @property
    def storage_target(self) -> str | Path:
        return self.storage_dsn if self.storage_dsn is not None else self.database  # type: ignore[return-value]

    @property
    def limits(self) -> IntakeLimits:
        return IntakeLimits(self.max_active_jobs, self.max_queued_jobs)


def create_app(
    settings: ApiSettings,
    *,
    authenticator: TenantAuthenticator | None = None,
    storage_factories: StorageFactories | None = None,
    publication_probe: Callable[[], None] | None = None,
    modification_service_factory=None,
    commercial_policy=None,
) -> FastAPI:
    if authenticator is None:
        raise ValueError("authenticator is required")
    app = FastAPI(title="Manim Quality API", version="1")
    app.state.settings = settings
    app.state.authenticator = authenticator
    app.state.publication_probe = publication_probe
    app.state.storage = storage_factories or create_storage_factories(
        settings.storage_target,
        publication_probe=publication_probe,
    )
    app.state.read_service = TenantReadService(app.state.storage.reads)
    app.state.modification_service_factory = modification_service_factory
    app.state.commercial_policy = commercial_policy
    app.include_router(jobs_router)
    app.include_router(revisions_router)
    app.include_router(modifications_router)
    return app
