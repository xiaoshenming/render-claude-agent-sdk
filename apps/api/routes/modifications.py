"""Tenant-scoped user modification preview and approval routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from manim_quality.modification.errors import (
    ModificationConflict,
    ModificationNotFound,
    ModificationStale,
)
from manim_quality.modification.service import ModificationFailed

from ..auth import AuthenticationError, TenantPrincipal
from ..schemas import ModificationApprovalResponse, ModificationDraftResponse
from .jobs import _check_length, _read_limited, _strict_json

router = APIRouter(prefix="/v1/quality/jobs")


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateModificationRequest(_StrictRequest):
    instruction: str = Field(min_length=1, max_length=20_000)
    target_scene_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=200)


class TransitionRequest(_StrictRequest):
    expected_version: int = Field(ge=0)


@router.post(
    "/{job_id}/modifications",
    status_code=201,
    response_model=ModificationDraftResponse,
)
async def create_modification(request: Request, job_id: str):
    principal = _principal(request)
    body = await _body(request)
    payload = _model(CreateModificationRequest, body)
    service = _service(request)
    try:
        draft = service.create_preview(
            tenant_id=principal.tenant_id,
            job_id=job_id,
            instruction=payload.instruction,
            target_scene_ids=payload.target_scene_ids,
            idempotency_key=payload.idempotency_key,
        )
        return draft.public_dict()
    except (ModificationConflict, ModificationStale) as error:
        raise HTTPException(409, str(error)) from error
    except (ModificationNotFound, KeyError) as error:
        raise HTTPException(404, "quality job not found") from error
    except (ModificationFailed, TypeError, ValueError) as error:
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(503, "modification request failed") from error
    finally:
        service.close()


@router.get(
    "/{job_id}/modifications/{draft_id}",
    response_model=ModificationDraftResponse,
)
def get_modification(request: Request, job_id: str, draft_id: str):
    principal = _principal(request)
    service = _service(request)
    try:
        return service.get(principal.tenant_id, job_id, draft_id).public_dict()
    except (ModificationNotFound, KeyError) as error:
        raise HTTPException(404, "modification draft not found") from error
    except Exception as error:
        raise HTTPException(503, "modification read failed") from error
    finally:
        service.close()


@router.post(
    "/{job_id}/modifications/{draft_id}/approve",
    response_model=ModificationApprovalResponse,
)
async def approve_modification(request: Request, job_id: str, draft_id: str):
    principal = _principal(request)
    payload = _model(TransitionRequest, await _body(request))
    service = _service(request)
    try:
        receipt = service.approve(
            principal.tenant_id,
            job_id,
            draft_id,
            expected_version=payload.expected_version,
        )
        return {
            "schema_version": 1,
            "draft": receipt.draft.public_dict(),
            "stage_run_id": receipt.stage_run_id,
            "quality_job_id": receipt.quality_job_id,
        }
    except (ModificationNotFound, KeyError) as error:
        raise HTTPException(404, "modification draft not found") from error
    except (ModificationConflict, ModificationStale, ModificationFailed) as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        raise HTTPException(503, "modification approval failed") from error
    finally:
        service.close()


@router.post(
    "/{job_id}/modifications/{draft_id}/discard",
    response_model=ModificationDraftResponse,
)
async def discard_modification(request: Request, job_id: str, draft_id: str):
    principal = _principal(request)
    payload = _model(TransitionRequest, await _body(request))
    service = _service(request)
    try:
        draft = service.discard(
            principal.tenant_id,
            job_id,
            draft_id,
            expected_version=payload.expected_version,
        )
        return draft.public_dict()
    except (ModificationNotFound, KeyError) as error:
        raise HTTPException(404, "modification draft not found") from error
    except (ModificationConflict, ModificationStale) as error:
        raise HTTPException(409, str(error)) from error
    except Exception as error:
        raise HTTPException(503, "modification discard failed") from error
    finally:
        service.close()


async def _body(request: Request) -> dict[str, object]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "application/json":
        raise HTTPException(415, "application/json required")
    maximum = request.app.state.settings.max_request_bytes
    _check_length(request, maximum)
    return _strict_json(await _read_limited(request, maximum))


def _model(model, payload):
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise HTTPException(422, "invalid modification request") from error


def _principal(request: Request) -> TenantPrincipal:
    try:
        return request.app.state.authenticator.authenticate(request.headers)
    except AuthenticationError as error:
        raise HTTPException(401, "authentication required") from error


def _service(request: Request):
    factory = request.app.state.modification_service_factory
    if factory is None:
        raise HTTPException(503, "modification service is unavailable")
    return factory()
