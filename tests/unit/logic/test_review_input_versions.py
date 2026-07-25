from pathlib import Path

from _reviewer_support import CODE, setup_evidence

from manim_quality.geometry.schemas import parse_geometry_snapshot
from manim_quality.logic.review_input import ReviewInputVersion, build_review_prompt
from manim_quality.revisions.fingerprint import code_hash


def geometry_snapshot():
    return parse_geometry_snapshot(
        {
            "schema_version": "manim-quality.geometry-snapshot.v1",
            "code_hash": code_hash(CODE),
            "scene_id": "Scene_02_Solve",
            "checkpoint_id": "final-visible",
            "provenance": "runtime_final",
            "objects": [
                {
                    "object_id": "answer_point",
                    "kind": "point",
                    "status": "known",
                    "reason_code": None,
                    "state": {"position": [1, 2, 0]},
                    "source": {
                        "scene_id": "Scene_02_Solve",
                        "line_start": 5,
                        "line_end": 5,
                        "excerpt": "answer = MathTex(...) ",
                    },
                }
            ],
        }
    )


def test_digest_v21_declares_decision_invariants_and_read_limit(tmp_path: Path) -> None:
    _, _, review_evidence = setup_evidence(tmp_path)
    prompt = build_review_prompt(
        evidence=review_evidence,
        candidate_code=CODE,
        candidate_path=Path("candidate.py"),
        manifest_path=Path("render_manifest.json"),
        input_version=ReviewInputVersion.DIGEST_V2_1,
    )

    assert '"input_version":"digest-v2-1"' in prompt
    assert "`needs_repair` => `blocked=true`" in prompt
    assert "At most one `Read` call" in prompt


def test_digest_v2_prompt_remains_frozen(tmp_path: Path) -> None:
    _, _, review_evidence = setup_evidence(tmp_path)
    prompt = build_review_prompt(
        evidence=review_evidence,
        candidate_code=CODE,
        candidate_path=Path("candidate.py"),
        manifest_path=Path("render_manifest.json"),
        input_version=ReviewInputVersion.DIGEST_V2,
    )

    assert '"input_version":"digest-v2"' in prompt
    assert "At most one `Read` call" not in prompt


def test_geometry_digest_exposes_only_compact_object_catalog(tmp_path: Path) -> None:
    _, _, review_evidence = setup_evidence(tmp_path)
    prompt = build_review_prompt(
        evidence=review_evidence,
        candidate_code=CODE,
        candidate_path=Path("candidate.py"),
        manifest_path=Path("render_manifest.json"),
        input_version=ReviewInputVersion.DIGEST_V2_2_GEOMETRY,
        geometry_snapshot=geometry_snapshot(),
    )

    assert '"input_version":"digest-v2-2-geometry"' in prompt
    assert '"object_id":"answer_point"' in prompt
    assert '"line_start":5' in prompt
    assert '"position"' not in prompt
    assert "At most two `inspect_geometry_relation` calls" in prompt
    assert "with explicit `offset` and `limit`" in prompt
    assert "Never make a third Read" in prompt
