"""Tenant-scoped API read service over the service delivery schema."""

from __future__ import annotations

from collections.abc import Callable

from manim_quality.storage.ports import TenantReadRepository


class TenantReadService:
    def __init__(self, factory: Callable[[], TenantReadRepository]) -> None:
        self._factory = factory

    def job(self, tenant_id: str, job_id: str) -> dict[str, object]:
        repository = self._factory()
        try:
            return repository.job(tenant_id, job_id)
        finally:
            repository.close()

    def revisions(self, tenant_id: str, job_id: str) -> list[dict[str, object]]:
        repository = self._factory()
        try:
            return repository.revisions(tenant_id, job_id)
        finally:
            repository.close()

    def evidence_hashes(self, tenant_id: str, job_id: str) -> list[str]:
        repository = self._factory()
        try:
            return repository.evidence_hashes(tenant_id, job_id)
        finally:
            repository.close()

    def certificate(self, tenant_id: str, job_id: str) -> tuple[str, bytes] | None:
        repository = self._factory()
        try:
            return repository.certificate(tenant_id, job_id)
        finally:
            repository.close()
