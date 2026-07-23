"""Execute one frozen Logic Reviewer shadow case and persist its evidence."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from claude_agent_sdk import __version__ as sdk_version

from manim_quality.agents import (
    AgentRunFailed,
    AgentRuntime,
    BudgetLimits,
    ClaudeSdkBackend,
    reviewer_profile,
)
from manim_quality.contracts import (
    PatchScope,
    QualitySubmission,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.logic.engine_adapter import build_engine_review_evidence
from manim_quality.logic.eval_manifest import FrozenEvalCase
from manim_quality.logic.evidence import build_logic_evidence
from manim_quality.logic.reporting import review_report_to_dict
from manim_quality.logic.review_input import ReviewInputVersion
from manim_quality.logic.reviewer import LogicReviewer, LogicReviewError
from manim_quality.logic.shadow import ShadowCaseResult
from manim_quality.revisions.fingerprint import (
    code_hash,
    evidence_hash,
    scene_fingerprints,
    semantic_fingerprint,
)

from ._logic_shadow_io import (
    JsonUsageSink,
    case_result,
    failed_result,
    write_json,
)
from ._logic_shadow_workspace import copy_scene_identity as _copy_scene_identity
from .workbench_e2e.relation_context import (
    load_or_build_relation_context,
    relation_prompt_evidence,
)
from .workbench_e2e.runtime_geometry import geometry_snapshot_for_review

QUALITY_RESERVED_OUTPUT_TOKENS = 40_000
REVIEWER_PROMPT_VERSION = "logic-reviewer-v6"
REVIEWER_PROMPT_VERSIONS = {
    ReviewInputVersion.EVIDENCE_V1.value: REVIEWER_PROMPT_VERSION,
    ReviewInputVersion.DIGEST_V2.value: "logic-reviewer-v7-digest",
    ReviewInputVersion.DIGEST_V2_1.value: "logic-reviewer-v7.1-digest",
    ReviewInputVersion.DIGEST_V2_2_GEOMETRY.value: "logic-reviewer-v8-geometry",
    ReviewInputVersion.FOCUSED_V2_3.value: "logic-reviewer-v9-focused",
}


@dataclass(frozen=True, slots=True)
class ShadowRunConfig:
    model: str
    provider_env: Mapping[str, str]
    output_root: Path
    input_version: ReviewInputVersion = ReviewInputVersion.EVIDENCE_V1
    runtime_python: str | None = None
    probe_source: Path | None = None


def run_shadow_case(
    case: FrozenEvalCase, *, dataset_root: Path, config: ShadowRunConfig
) -> ShadowCaseResult:
    case_dir = _case_output_dir(config.output_root, case.sample_id)
    sink = JsonUsageSink(case_dir / "agent_call.json")
    try:
        with tempfile.TemporaryDirectory(
            prefix="manim-quality-shadow-", ignore_cleanup_errors=True
        ) as temp:
            workspace = Path(temp)
            candidate_source = _required(case, "candidate.py", dataset_root)
            candidate = workspace / "candidate.py"
            shutil.copyfile(candidate_source, candidate)
            code = candidate.read_text(encoding="utf-8")
            problem = _required(case, "problem_text.txt", dataset_root).read_text(
                encoding="utf-8"
            )
            (workspace / "problem_text.txt").write_text(problem, encoding="utf-8")
            _copy_scene_identity(case, dataset_root, workspace)
            expected = _optional_text(case, "expected_solution.txt", dataset_root)
            planning = _optional_json(case, "planning.json", dataset_root)
            planning = dict(planning or {})
            render_manifest = _render_manifest(case, code)
            manifest_path = workspace / "render_manifest.json"
            manifest_path.write_bytes(render_manifest)
            relation = load_or_build_relation_context(
                cache_path=dataset_root / "expected_actual_relations.cache.json",
                sample_id=case.sample_id,
                code=code,
                problem=problem,
                expected=expected,
                planning=planning,
                workspace=workspace,
                model=config.model,
                provider_env=config.provider_env,
                output_dir=case_dir,
            )
            prompt_relation = relation_prompt_evidence(relation)
            if prompt_relation is not None:
                planning["expected_actual_relations"] = prompt_relation
            evidence = _evidence(
                code, problem, expected, planning, render_manifest, case, workspace
            )
            runtime = AgentRuntime(
                ClaudeSdkBackend(provider_env=config.provider_env),
                sink,
                _limits(config.input_version),
            )
            reviewer = LogicReviewer(
                runtime=runtime,
                input_version=config.input_version,
                profile=reviewer_profile(
                    model=config.model,
                    prompt_version=REVIEWER_PROMPT_VERSIONS[config.input_version.value],
                    tool_version=f"claude-agent-sdk-{sdk_version}-read-v1",
                ),
            )
            estimate = max(1_000, (len(code.encode("utf-8")) + len(problem)) // 2)
            result = reviewer.review(
                run_id=f"shadow-{case.sample_id}",
                evidence=evidence,
                workspace=workspace,
                candidate_path=candidate,
                render_manifest_path=manifest_path,
                estimated_input_tokens=estimate,
                reserved_output_tokens=QUALITY_RESERVED_OUTPUT_TOKENS,
                reserved_cache_read_tokens=estimate,
                reserved_cache_write_tokens=estimate,
                geometry_snapshot=(
                    geometry_snapshot_for_review(
                        code=code,
                        candidate=candidate_source,
                        runtime_python=config.runtime_python,
                        probe_source=config.probe_source,
                        output_dir=case_dir / "runtime_geometry",
                    )
                    if _uses_geometry(config.input_version)
                    else None
                ),
            )
        write_json(
            case_dir / "review_report.json", review_report_to_dict(result.report)
        )
        return case_result(
            case,
            result.call_record,
            result.report.decision,
            result.report.issues,
        )
    except AgentRunFailed as error:
        return failed_result(case, error.record, str(error))
    except LogicReviewError as error:
        return failed_result(case, error.call_record, str(error))
    except Exception as error:
        return failed_result(case, sink.record, f"{type(error).__name__}: {error}")


def _evidence(
    code: str,
    problem: str,
    expected: str | None,
    planning: dict[str, object] | None,
    manifest: bytes,
    case: FrozenEvalCase,
    workspace: Path,
):
    submission = QualitySubmission(
        job_id=case.sample_id,
        tenant_id="offline-eval",
        candidate_code_ref="candidate.py",
        problem_text=problem,
        planning=planning or {"review_scope": "logic_only"},
        expected_answer=expected,
        render_manifest_ref="render_manifest.json",
        asset_manifest_ref=None,
        callback_url=None,
        idempotency_key=f"shadow-{case.sample_id}",
    )
    revision = Revision(
        revision_id=f"baseline-{case.sample_id}",
        parent_revision_id=None,
        stage=RevisionStage.BASELINE,
        code_hash=code_hash(code),
        semantic_fingerprint=semantic_fingerprint(code),
        scene_hashes=scene_fingerprints(code),
        render_manifest_hash=evidence_hash(manifest),
        changed_scene_ids=(),
        patch_scope=PatchScope.FULL_CANDIDATE,
        created_by=RevisionCreator.GENERATION_ADAPTER,
        attempt=0,
    )
    return build_logic_evidence(
        code=code,
        submission=submission,
        revision=revision,
        render_manifest=manifest,
        engine_evidence=build_engine_review_evidence(workspace),
    )


def _render_manifest(case: FrozenEvalCase, code: str) -> bytes:
    video = case.artifacts.get("before.mp4")
    data = {
        "schema_version": "offline-shadow-render-binding-v1",
        "candidate_code_hash": code_hash(code),
        "source_video_hash": video.sha256 if video is not None else None,
        "status": (
            "frozen_rendered_candidate"
            if video is not None
            else "code_only_mutation_probe"
        ),
    }
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _case_output_dir(output_root: Path, sample_id: str) -> Path:
    root = (Path(output_root).resolve() / "cases").resolve()
    path = (root / sample_id).resolve()
    if not path.is_relative_to(root):
        raise ValueError("sample output path escapes output root")
    return path


def _limits(
    input_version: ReviewInputVersion = ReviewInputVersion.EVIDENCE_V1,
) -> BudgetLimits:
    geometry = _uses_geometry(input_version)
    return BudgetLimits(
        max_context_bytes=250_000,
        max_turns=10 if geometry else 8,
        max_tool_calls=12,
        max_elapsed_ms=240_000,
        max_input_tokens=200_000,
        max_output_tokens=80_000,
        max_cache_read_tokens=200_000,
        max_cache_write_tokens=200_000,
        max_total_tokens=400_000,
    )


def _uses_geometry(input_version: ReviewInputVersion) -> bool:
    return input_version in {
        ReviewInputVersion.DIGEST_V2_2_GEOMETRY,
        ReviewInputVersion.FOCUSED_V2_3,
    }


def _required(case: FrozenEvalCase, name: str, root: Path) -> Path:
    artifact = case.artifacts.get(name)
    if artifact is None:
        raise ValueError(f"missing required artifact: {name}")
    return artifact.resolve_verified(root)


def _optional_text(case: FrozenEvalCase, name: str, root: Path) -> str | None:
    artifact = case.artifacts.get(name)
    if artifact is None:
        return None
    return artifact.resolve_verified(root).read_text(encoding="utf-8")


def _optional_json(case: FrozenEvalCase, name: str, root: Path) -> dict[str, object] | None:
    artifact = case.artifacts.get(name)
    if artifact is None:
        return None
    value = json.loads(artifact.resolve_verified(root).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return value
