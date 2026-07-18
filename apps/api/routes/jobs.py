"""Submission and status routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from manim_quality.storage.intake import (
    IntakeConflict,
    IntakeQuotaExceeded,
    SubmissionNotFound,
)
from manim_quality.storage.queue_models import IntakeLimits

from ..auth import AuthenticationError, TenantPrincipal
from ..schemas import JobResponse, ReceiptResponse

router = APIRouter(prefix="/v1/quality/jobs")


@router.post("", status_code=202, response_model=ReceiptResponse)
async def create_job(
    request: Request,
) -> dict[str, object]:
    principal = _principal(request)
    settings = request.app.state.settings
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "application/json":
        raise HTTPException(415, "application/json required")
    _check_length(request, settings.max_request_bytes)
    body = await _read_limited(request, settings.max_request_bytes)
    payload = _strict_json(body)
    if payload.get("tenant_id") != principal.tenant_id:
        raise HTTPException(403, "tenant identity mismatch")
    repository = request.app.state.storage.intake()
    try:
        receipt = repository.submit(payload, _intake_limits(request, principal))
        return receipt.to_dict()
    except IntakeConflict as error:
        raise HTTPException(409, str(error)) from error
    except IntakeQuotaExceeded as error:
        raise HTTPException(429, str(error)) from error
    except (TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(503, "submission transaction failed") from error
    finally:
        repository.close()


@router.get("/{job_id}", response_model=JobResponse)
def get_job(request: Request, job_id: str):
    principal = _principal(request)
    try:
        return request.app.state.read_service.job(principal.tenant_id, job_id)
    except SubmissionNotFound as error:
        raise HTTPException(404, "job not found") from error


def _check_length(request: Request, maximum: int) -> None:
    value = request.headers.get("content-length")
    if value is None:
        return
    try:
        length = int(value)
    except ValueError as error:
        raise HTTPException(400, "invalid content-length") from error
    if length < 0 or length > maximum:
        raise HTTPException(413, "request body too large")


async def _read_limited(request: Request, maximum: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > maximum:
            raise HTTPException(413, "request body too large")
        chunks.append(chunk)
    return b"".join(chunks)


def _principal(request: Request) -> TenantPrincipal:
    try:
        return request.app.state.authenticator.authenticate(request.headers)
    except AuthenticationError as error:
        raise HTTPException(401, "authentication required") from error


def _strict_json(body: bytes) -> dict[str, object]:
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(body, object_pairs_hook=object_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise HTTPException(400, "invalid JSON") from error
    if type(value) is not dict:
        raise HTTPException(422, "QualitySubmission must be an object")
    return value


def _intake_limits(request: Request, principal: TenantPrincipal):
    settings = request.app.state.settings
    policy = request.app.state.commercial_policy
    if policy is None:
        return settings.limits
    limits = policy.limits_for(principal.tenant_id)
    return IntakeLimits(
        min(settings.max_active_jobs, limits.max_concurrent_jobs),
        min(settings.max_queued_jobs, limits.max_concurrent_jobs),
    )
