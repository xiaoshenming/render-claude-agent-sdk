"""Strict queue payload parser for approved modification quality work."""

from __future__ import annotations

import json
from collections.abc import Mapping

from manim_quality.orchestrator.models import ExecutionRequest
from manim_quality.orchestrator.versioning import AgentIdentity, VersionBindings
from manim_quality.storage.queue_models import QueueItem

_FIELDS = frozenset(
    {
        "schema_version",
        "job_id",
        "stage_run_id",
        "source_revision_id",
        "source_code",
        "code_ref",
        "render_manifest_ref",
        "question_hash",
        "plan_hash",
        "render_config_hash",
        "assets_hash",
        "external_dependencies_hash",
        "ordered_scene_ids",
        "environment_evidence_hash",
        "versions",
    }
)


def execution_request_from_queue(item: QueueItem) -> ExecutionRequest:
    if not isinstance(item, QueueItem):
        raise TypeError("item must be QueueItem")
    try:
        payload = json.loads(item.payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid modification quality payload") from error
    if not isinstance(payload, dict) or set(payload) != _FIELDS:
        raise ValueError("modification quality payload fields differ")
    if payload["schema_version"] != 1:
        raise ValueError("unsupported modification quality payload")
    if payload["job_id"] != item.job_id or payload["stage_run_id"] != item.stage_run_id:
        raise ValueError("modification queue identity mismatch")
    _text(payload["source_revision_id"], "source_revision_id")
    return ExecutionRequest(
        job_id=item.job_id,
        run_id=item.stage_run_id,
        request_hash=item.request_hash,
        question_hash=payload["question_hash"],
        plan_hash=payload["plan_hash"],
        source_code=payload["source_code"],
        code_ref=payload["code_ref"],
        render_manifest_ref=payload["render_manifest_ref"],
        render_config_hash=payload["render_config_hash"],
        assets_hash=payload["assets_hash"],
        external_dependencies_hash=payload["external_dependencies_hash"],
        ordered_scene_ids=tuple(payload["ordered_scene_ids"]),
        environment_evidence_hash=payload["environment_evidence_hash"],
        versions=_versions(payload["versions"]),
    )


def _versions(value: object) -> VersionBindings:
    if not isinstance(value, Mapping):
        raise ValueError("versions must be an object")
    fields = VersionBindings.__dataclass_fields__
    if set(value) != set(fields):
        raise ValueError("version binding fields differ")
    agents = {"logic_review", "logic_repair", "logic_verifier", "layout_repair"}
    payload = {
        name: _agent(item, name) if name in agents else item
        for name, item in value.items()
    }
    return VersionBindings(**payload)


def _agent(value: object, name: str) -> AgentIdentity:
    if not isinstance(value, Mapping) or set(value) != {
        "model_version",
        "prompt_version",
        "tool_version",
    }:
        raise ValueError(f"{name} identity fields differ")
    return AgentIdentity(
        value["model_version"], value["prompt_version"], value["tool_version"]
    )


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be non-empty")
