"""Tenant-scoped revision and evidence routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from manim_quality.storage.intake import SubmissionNotFound

from ..schemas import CertificateResponse, EvidenceResponse, RevisionListResponse
from .jobs import _principal

router = APIRouter(prefix="/v1/quality/jobs")


@router.get("/{job_id}/revisions", response_model=RevisionListResponse)
def revisions(request: Request, job_id: str):
    principal = _principal(request)
    try:
        items = request.app.state.read_service.revisions(principal.tenant_id, job_id)
        return {"schema_version": 1, "job_id": job_id, "items": items}
    except SubmissionNotFound as error:
        raise HTTPException(404, "job not found") from error


@router.get("/{job_id}/evidence", response_model=EvidenceResponse)
def evidence(request: Request, job_id: str):
    principal = _principal(request)
    try:
        items = request.app.state.read_service.evidence_hashes(
            principal.tenant_id, job_id
        )
        return {"schema_version": 1, "job_id": job_id, "evidence_hashes": items}
    except SubmissionNotFound as error:
        raise HTTPException(404, "job not found") from error


@router.get("/{job_id}/certificate", response_model=CertificateResponse)
def certificate(request: Request, job_id: str):
    principal = _principal(request)
    try:
        item = request.app.state.read_service.certificate(principal.tenant_id, job_id)
    except SubmissionNotFound as error:
        raise HTTPException(404, "job not found") from error
    if item is None:
        raise HTTPException(409, {"reason": "NOT_READY", "state": "PENDING"})
    evidence_hash, payload = item
    return {
        "schema_version": 1,
        "job_id": job_id,
        "evidence_hash": evidence_hash,
        "payload": json.loads(payload),
    }
