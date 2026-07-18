import json
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from manim_quality.contracts import (
    PatchScope,
    QualitySubmission,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.logic._provenance import ProvenancedValue
from manim_quality.logic.engine_adapter import build_engine_review_evidence
from manim_quality.logic.evidence import EvidenceBuildError, build_logic_evidence
from manim_quality.revisions.fingerprint import (
    code_hash,
    evidence_hash,
    semantic_fingerprint,
)

CODE = """from manim import *

class BaseConfigScene(Scene):
    def helper(self):
        return "共享配置"

class Scene_01_Question(BaseConfigScene):
    def construct(self):
        title = Text("求 x 的值")
        formula = MathTex("x+2=12")
        self.add(title, formula)

class LessonSummary(Scene):
    def construct(self):
        answer = MathTex("x=10")
        self.add(answer)
"""


def engine_evidence(source: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="logic-evidence-test-") as temp:
        root = Path(temp)
        (root / "candidate.py").write_text(source, encoding="utf-8")
        return build_engine_review_evidence(root)


ENGINE_EVIDENCE = engine_evidence(CODE)


def submission(
    *,
    render_ref: str | None = "artifacts/render.json",
    expected_answer: str | None = "x=10",
) -> QualitySubmission:
    return QualitySubmission(
        job_id="job-1",
        tenant_id="tenant-1",
        candidate_code_ref="artifacts/candidate.py",
        problem_text="解方程 x+2=12。",
        planning={"method": "移项", "steps": ["两边减 2"]},
        expected_answer=expected_answer,
        render_manifest_ref=render_ref,
        asset_manifest_ref=None,
        callback_url=None,
        idempotency_key="idem-1",
    )


def revision(source: str, manifest: bytes) -> Revision:
    try:
        semantic_hash = semantic_fingerprint(source)
    except ValueError:
        semantic_hash = semantic_fingerprint("pass\n")
    return Revision(
        revision_id="rev-1",
        parent_revision_id=None,
        stage=RevisionStage.BASELINE,
        code_hash=code_hash(source),
        semantic_fingerprint=semantic_hash,
        scene_hashes={},
        render_manifest_hash=evidence_hash(manifest),
        changed_scene_ids=(),
        patch_scope=PatchScope.FULL_CANDIDATE,
        created_by=RevisionCreator.GENERATION_ADAPTER,
        attempt=0,
    )


def test_evidence_binds_provenance_manifest_and_compact_scene_index() -> None:
    manifest = json.dumps(
        {"renderer": "manim-0.19", "scenes": ["Scene_01_Question", "LessonSummary"]},
        ensure_ascii=False,
    ).encode("utf-8")

    evidence = build_logic_evidence(
        code=CODE,
        submission=submission(),
        revision=revision(CODE, manifest),
        render_manifest=manifest,
        engine_evidence=ENGINE_EVIDENCE,
    )

    assert evidence.revision_id == "rev-1"
    assert evidence.code_hash == code_hash(CODE)
    assert evidence.render_manifest_hash == evidence_hash(manifest)
    assert evidence.problem.source_ref == "submission:job-1:problem_text"
    assert evidence.planning.source_ref == "submission:job-1:planning"
    assert evidence.expected_answer is not None
    assert evidence.expected_answer.source_ref == "submission:job-1:expected_answer"
    assert [scene.scene_id for scene in evidence.scenes] == [
        "Scene_01_Question",
        "LessonSummary",
    ]
    assert evidence.scenes[0].texts == ("求 x 的值",)
    assert evidence.scenes[0].formulas == ("x+2=12",)
    assert evidence.scenes[0].line_start < evidence.scenes[0].line_end
    prompt_evidence = evidence.to_prompt_dict()
    assert set(prompt_evidence) == {
        "problem",
        "planning",
        "expected_answer",
        "engine_evidence",
        "scenes",
    }
    assert prompt_evidence["problem"] == {"value": "解方程 x+2=12。"}
    encoded_prompt = json.dumps(prompt_evidence, ensure_ascii=False)
    assert "job-1" not in encoded_prompt
    assert "rev-1" not in encoded_prompt
    assert "sha256:" not in encoded_prompt
    assert "code" not in prompt_evidence["scenes"][0]
    assert (
        prompt_evidence["engine_evidence"]["input_policy"][
            "external_diagnosis_included"
        ]
        is False
    )


def test_evidence_rejects_non_object_planning_before_output_binding() -> None:
    manifest = b'{"rendered": true}'
    evidence = build_logic_evidence(
        code=CODE,
        submission=submission(),
        revision=revision(CODE, manifest),
        render_manifest=manifest,
        engine_evidence=ENGINE_EVIDENCE,
    )
    invalid = ProvenancedValue(
        value="not an object",
        source_ref=evidence.planning.source_ref,
        content_hash=evidence.planning.content_hash,
    )

    with pytest.raises(TypeError, match="planning evidence must be an object"):
        replace(evidence, planning=invalid)


def test_evidence_rejects_invalid_bound_value_types() -> None:
    manifest = b'{"scenes":["Scene_01_Question","LessonSummary"]}'
    evidence = build_logic_evidence(
        code=CODE,
        submission=submission(),
        revision=revision(CODE, manifest),
        render_manifest=manifest,
        engine_evidence=ENGINE_EVIDENCE,
    )

    for changes in (
        {"problem": object()},
        {"expected_answer": object()},
        {"scenes": ()},
        {"scenes": (evidence.scenes[0], evidence.scenes[0])},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(evidence, **changes)


def test_evidence_builder_rejects_invalid_contract_types() -> None:
    manifest = b'{"scenes":[]}'
    with pytest.raises(TypeError, match="submission"):
        build_logic_evidence(
            code=CODE,
            submission=object(),  # type: ignore[arg-type]
            revision=revision(CODE, manifest),
            render_manifest=manifest,
            engine_evidence=ENGINE_EVIDENCE,
        )
    with pytest.raises(TypeError, match="revision"):
        build_logic_evidence(
            code=CODE,
            submission=submission(),
            revision=object(),  # type: ignore[arg-type]
            render_manifest=manifest,
            engine_evidence=ENGINE_EVIDENCE,
        )
    with pytest.raises(TypeError, match="render_manifest"):
        build_logic_evidence(
            code=CODE,
            submission=submission(),
            revision=revision(CODE, manifest),
            render_manifest="not-bytes",  # type: ignore[arg-type]
            engine_evidence=ENGINE_EVIDENCE,
        )


@pytest.mark.parametrize("mismatch", ["code", "manifest"])
def test_evidence_rejects_stale_revision_bindings(mismatch: str) -> None:
    manifest = b'{"scenes":[]}'
    source = CODE if mismatch != "code" else CODE.replace("x=10", "x=9")
    manifest_bytes = manifest if mismatch != "manifest" else b'{"scenes":["other"]}'

    with pytest.raises(EvidenceBuildError, match="hash"):
        build_logic_evidence(
            code=source,
            submission=submission(),
            revision=revision(CODE, manifest),
            render_manifest=manifest_bytes,
            engine_evidence=ENGINE_EVIDENCE,
        )


def test_evidence_rejects_engine_facts_from_another_candidate() -> None:
    manifest = b'{"scenes":[]}'
    stale_engine_evidence = {
        **ENGINE_EVIDENCE,
        "candidate_code_hash": "sha256:" + "f" * 64,
    }

    with pytest.raises(ValueError, match="candidate code hash"):
        build_logic_evidence(
            code=CODE,
            submission=submission(),
            revision=revision(CODE, manifest),
            render_manifest=manifest,
            engine_evidence=stale_engine_evidence,
        )


def test_evidence_rejects_fabricated_facts_for_matching_candidate() -> None:
    manifest = b'{"scenes":[]}'
    fabricated = {
        **ENGINE_EVIDENCE,
        "deterministic_logic_facts": {"fabricated_mismatch_count": 1},
    }

    with pytest.raises(ValueError, match="deterministic facts"):
        build_logic_evidence(
            code=CODE,
            submission=submission(),
            revision=revision(CODE, manifest),
            render_manifest=manifest,
            engine_evidence=fabricated,
        )


def test_evidence_requires_render_provenance_and_parseable_scene_code() -> None:
    manifest = b'{"scenes":[]}'
    with pytest.raises(EvidenceBuildError, match="render_manifest_ref"):
        build_logic_evidence(
            code=CODE,
            submission=submission(render_ref=None),
            revision=revision(CODE, manifest),
            render_manifest=manifest,
            engine_evidence=ENGINE_EVIDENCE,
        )
    with pytest.raises(ValueError, match="not parseable"):
        build_logic_evidence(
            code="class Broken(",
            submission=submission(),
            revision=revision("class Broken(", manifest),
            render_manifest=manifest,
            engine_evidence=engine_evidence("class Broken("),
        )


@pytest.mark.parametrize("manifest", [b"not-json", b"[]", b"\xff"])
def test_evidence_rejects_unreadable_or_non_object_manifest(manifest: bytes) -> None:
    with pytest.raises(EvidenceBuildError, match="JSON object"):
        build_logic_evidence(
            code=CODE,
            submission=submission(),
            revision=revision(CODE, manifest),
            render_manifest=manifest,
            engine_evidence=ENGINE_EVIDENCE,
        )


def test_evidence_preserves_missing_expected_answer_without_inventing_one() -> None:
    manifest = b'{"scenes":["Scene_01_Question","LessonSummary"]}'

    evidence = build_logic_evidence(
        code=CODE,
        submission=submission(expected_answer=None),
        revision=revision(CODE, manifest),
        render_manifest=manifest,
        engine_evidence=ENGINE_EVIDENCE,
    )

    assert evidence.expected_answer is None
    assert evidence.to_prompt_dict()["expected_answer"] is None


def test_evidence_rejects_python_without_concrete_scene() -> None:
    source = "VALUE = 1\n"
    manifest = b'{"scenes":[]}'

    with pytest.raises(EvidenceBuildError, match="no concrete Scene"):
        build_logic_evidence(
            code=source,
            submission=submission(),
            revision=revision(source, manifest),
            render_manifest=manifest,
            engine_evidence=engine_evidence(source),
        )
