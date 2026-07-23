import json
from pathlib import Path

from evals import _logic_shadow_case
from evals._logic_shadow_io import _call_record_dict, _hits_target_lines
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, ToolCallRecord
from manim_quality.logic.eval_manifest import EvalArtifact, FrozenEvalCase
from manim_quality.logic.review_input import ReviewInputVersion
from manim_quality.logic.schemas import CitationArtifact, EvidenceCitation
from manim_quality.logic.shadow import EvalTruth
from manim_quality.revisions.fingerprint import sha256_bytes


def test_shadow_policy_allows_bounded_quality_first_reviewer_reasoning() -> None:
    limits = _logic_shadow_case._limits()

    assert _logic_shadow_case.REVIEWER_PROMPT_VERSION == "logic-reviewer-v6"
    assert _logic_shadow_case.QUALITY_RESERVED_OUTPUT_TOKENS == 40_000
    assert limits.max_context_bytes == 250_000
    assert limits.max_input_tokens == 200_000
    assert limits.max_output_tokens == 80_000
    assert limits.max_total_tokens == 400_000
    assert limits.max_turns == 8
    geometry_limits = _logic_shadow_case._limits(
        ReviewInputVersion.DIGEST_V2_2_GEOMETRY
    )
    assert geometry_limits.max_turns == 10
    assert geometry_limits.max_tool_calls == 12
    focused_limits = _logic_shadow_case._limits(ReviewInputVersion.FOCUSED_V2_3)
    assert focused_limits.max_turns == 10


def test_shadow_review_versions_are_explicit_and_rollback_safe() -> None:
    assert _logic_shadow_case.REVIEWER_PROMPT_VERSIONS == {
        "evidence-v1": "logic-reviewer-v6",
        "digest-v2": "logic-reviewer-v7-digest",
        "digest-v2-1": "logic-reviewer-v7.1-digest",
        "digest-v2-2-geometry": "logic-reviewer-v8-geometry",
        "focused-v2-3": "logic-reviewer-v9-focused",
    }


def test_shadow_copies_only_verified_scene_identity(tmp_path: Path) -> None:
    source = tmp_path / "pack" / "case_manifest.json"
    source.parent.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "scene_name": "DemoScene",
                "visible_error_description": "must not reach reviewer",
            }
        ),
        encoding="utf-8",
    )
    case = FrozenEvalCase(
        sample_id="case-1",
        truth=EvalTruth.KNOWN_BAD,
        artifacts={
            "case_manifest.json": EvalArtifact(
                relative_path="pack/case_manifest.json",
                sha256=sha256_bytes(source.read_bytes()),
            )
        },
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    _logic_shadow_case._copy_scene_identity(case, tmp_path, workspace)

    copied = json.loads((workspace / "case_manifest.json").read_text(encoding="utf-8"))
    assert copied == {"scene_name": "DemoScene"}


def test_bad_render_manifest_does_not_bind_original_video_to_mutated_code() -> None:
    case = FrozenEvalCase(
        sample_id="bad-1",
        truth=EvalTruth.KNOWN_BAD,
        artifacts={
            "source_correct.mp4": EvalArtifact(
                relative_path="pack/source_correct.mp4",
                sha256="sha256:" + "a" * 64,
            )
        },
        target_lines=(12,),
    )

    manifest = json.loads(_logic_shadow_case._render_manifest(case, "pass\n"))

    assert manifest["status"] == "code_only_mutation_probe"
    assert manifest["source_video_hash"] is None


def test_bad_render_manifest_binds_a_rendered_mutant_without_truth_leakage() -> None:
    rendered_hash = "sha256:" + "b" * 64
    case = FrozenEvalCase(
        sample_id="bad-rendered-1",
        truth=EvalTruth.KNOWN_BAD,
        artifacts={
            "before.mp4": EvalArtifact(
                relative_path="pack/before.mp4",
                sha256=rendered_hash,
            )
        },
        target_lines=(12,),
    )

    manifest = json.loads(_logic_shadow_case._render_manifest(case, "pass\n"))

    assert manifest["status"] == "frozen_rendered_candidate"
    assert manifest["source_video_hash"] == rendered_hash


def test_target_hit_requires_candidate_citation_to_cover_mutation_line() -> None:
    citation = EvidenceCitation(
        artifact=CitationArtifact.CANDIDATE_CODE,
        source_ref="candidate.py",
        source_hash="sha256:" + "a" * 64,
        excerpt="wrong relation",
        scene_id="Demo",
        line_start=20,
        line_end=22,
    )

    assert _hits_target_lines((citation,), (21,)) is True
    assert _hits_target_lines((citation,), (12,)) is False


def test_geometry_shadow_builds_diagnosis_free_static_snapshot(
    tmp_path: Path,
) -> None:
    code = """from manim import *
import numpy as np

class Demo(Scene):
    def construct(self):
        A = np.array([0, 0, 0])
        B = np.array([1, 0, 0])
        segment = Line(A, B)
"""
    (tmp_path / "case_manifest.json").write_text(
        json.dumps({"scene_name": "Demo"}), encoding="utf-8"
    )

    snapshot = _logic_shadow_case._geometry_snapshot(
        ReviewInputVersion.DIGEST_V2_2_GEOMETRY,
        code,
        tmp_path,
    )

    assert snapshot is not None
    assert snapshot.provenance == "static_initial_state"
    assert {item.object_id for item in snapshot.objects} == {"A", "B", "segment"}
    assert (
        _logic_shadow_case._geometry_snapshot(
            ReviewInputVersion.DIGEST_V2_1, code, tmp_path
        )
        is None
    )


def test_shadow_audit_persists_read_tool_result_fingerprint() -> None:
    record = AgentCallRecord(
        run_id="run-1",
        role="reviewer",
        model="model",
        prompt="prompt",
        prompt_version="v1",
        schema_version="v1",
        tool_version="v1",
        structured_output=None,
        tool_calls=(
            ToolCallRecord(
                name="mcp__geometry__inspect_geometry_relation",
                input={"relation": "parallel", "operands": ["a", "b"]},
                allowed=True,
                result_status="ok",
                result_hash="sha256:" + "a" * 64,
            ),
        ),
        usage=TokenUsage(),
        turns=1,
        observed_model_rounds=1,
        elapsed_ms=1,
        error=None,
    )

    call = _call_record_dict(record)["tool_calls"][0]
    assert call["result_status"] == "ok"
    assert call["result_hash"] == "sha256:" + "a" * 64
