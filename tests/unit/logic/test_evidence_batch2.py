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
