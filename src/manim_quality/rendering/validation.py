"""Fail-closed source, environment, and reuse preparation."""

from __future__ import annotations

from dataclasses import dataclass

from .impact import SourceImpact, analyze_source
from .interfaces import (
    CertificationAuthority,
    EnvironmentAuthority,
    EnvironmentEvidence,
    RenderFailureStage,
    RenderRequest,
)
from .slices import RenderPlan, build_render_plan, restrict_reuse


@dataclass(frozen=True, slots=True)
class RenderPreparation:
    plan: RenderPlan
    environment: EnvironmentEvidence | None
    failure_stage: RenderFailureStage | None = None
    failure_detail: object = ""


def prepare_render(
    request: RenderRequest,
    environment_authority: EnvironmentAuthority,
    certification_authority: CertificationAuthority,
) -> RenderPreparation:
    fail_plan = fail_closed_plan(request, "impact_not_verified")
    environment, failure = _resolve_environment(
        request, environment_authority, fail_plan
    )
    if failure is not None:
        return failure
    impact, failure = _resolve_impact(request, fail_plan, environment)
    if failure is not None:
        return failure
    plan = build_render_plan(request, impact, environment)
    return _authorize(plan, request, environment, certification_authority)


def fail_closed_plan(request: RenderRequest, reason: str) -> RenderPlan:
    return RenderPlan(tuple(request.ordered_scene_ids), {}, True, (reason,))


def _resolve_environment(
    request: RenderRequest,
    authority: EnvironmentAuthority,
    fail_plan: RenderPlan,
) -> tuple[EnvironmentEvidence | None, RenderPreparation | None]:
    try:
        environment = authority.resolve_environment(request)
    except Exception as error:
        return None, _failed(fail_plan, RenderFailureStage.ENVIRONMENT, error)
    if not isinstance(environment, EnvironmentEvidence):
        return None, _failed(
            fail_plan,
            RenderFailureStage.ENVIRONMENT,
            "environment authority returned invalid evidence",
        )
    if environment.assets_hash != request.assets_hash:
        return None, _failed(
            fail_plan,
            RenderFailureStage.ENVIRONMENT,
            "declared assets_hash differs from authoritative evidence",
        )
    return environment, None


def _resolve_impact(
    request: RenderRequest,
    fail_plan: RenderPlan,
    environment: EnvironmentEvidence,
) -> tuple[SourceImpact | None, RenderPreparation | None]:
    try:
        impact = analyze_source(request.source_code, request.ordered_scene_ids)
    except Exception as error:
        return None, _failed(
            fail_plan, RenderFailureStage.IMPACT_ANALYSIS, error, environment
        )
    if not _impact_matches(request, impact):
        return None, _failed(
            fail_plan,
            RenderFailureStage.IMPACT_ANALYSIS,
            "declared Scene identities do not match source",
            environment,
        )
    return impact, None


def _authorize(
    plan: RenderPlan,
    request: RenderRequest,
    environment: EnvironmentEvidence,
    authority: CertificationAuthority,
) -> RenderPreparation:
    authorized: set[str] = set()
    for scene_id, item in plan.reusable_slices.items():
        try:
            decision = authority.authorize_reuse(item)
        except Exception as error:
            return _failed(plan, RenderFailureStage.CERTIFICATION, error, environment)
        if type(decision) is not bool:
            return _failed(
                plan,
                RenderFailureStage.CERTIFICATION,
                f"{scene_id}: authority returned an invalid decision",
                environment,
            )
        if decision:
            authorized.add(scene_id)
    restricted = restrict_reuse(plan, request.ordered_scene_ids, authorized)
    return RenderPreparation(restricted, environment)


def _impact_matches(request: RenderRequest, impact: SourceImpact) -> bool:
    return set(request.ordered_scene_ids) == set(impact.scene_hashes) and dict(
        request.scene_hashes
    ) == dict(impact.scene_hashes)


def _failed(
    plan: RenderPlan,
    stage: RenderFailureStage,
    detail: object,
    environment: EnvironmentEvidence | None = None,
) -> RenderPreparation:
    return RenderPreparation(plan, environment, stage, detail)
