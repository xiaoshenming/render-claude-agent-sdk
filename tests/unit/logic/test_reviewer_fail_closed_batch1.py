from dataclasses import replace
from pathlib import Path

import pytest
from _reviewer_support import (
    CODE,
    MemorySink,
    PayloadBackend,
    add_citation,
    candidate_citation,
    issue_entry,
    issue_payload,
    limits,
    reviewer,
    service,
    setup_evidence,
)

from manim_quality.agents.profile import coder_profile, reviewer_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.logic._errors import ReviewOutputValidationError
from manim_quality.logic._review_output import bind_review_output
from manim_quality.logic.reviewer import LogicReviewer, LogicReviewError
from manim_quality.revisions.fingerprint import evidence_hash



@pytest.mark.parametrize(
    "payload",
    [
        {
            "decision": "pass",
            "blocked": True,
            "requires_human_review": False,
            "summary": "pass",
            "review_gaps": [],
            "issues": [],
        },
        issue_payload(excerpt='MathTex("x=999")'),
    ],
)
def test_reviewer_fails_closed_on_contradiction_or_unverifiable_citation(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    with pytest.raises(LogicReviewError):
        reviewer(tmp_path, payload)

def test_reviewer_rejects_non_code_excerpt_absent_from_source(tmp_path: Path) -> None:
    payload = issue_payload()
    add_citation(payload, artifact="problem_text", excerpt="not in the problem")

    with pytest.raises(LogicReviewError, match="absent from problem_text"):
        reviewer(tmp_path, payload)

def test_review_output_uses_typed_model_validation_error(tmp_path: Path) -> None:
    candidate, manifest, evidence = setup_evidence(tmp_path)

    with pytest.raises(ReviewOutputValidationError, match="fields do not match"):
        bind_review_output(
            {"unexpected": True},
            review_id="typed-error",
            evidence=evidence,
            candidate_code=candidate.read_text(encoding="utf-8"),
            render_manifest_text=manifest.read_text(encoding="utf-8"),
        )

@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("line_start", None, "require line bounds"),
        ("line_end", 999, "line bounds are invalid"),
        ("line_start", "5", "integer or null"),
        ("artifact", 7, "artifact must be a string"),
        ("artifact", "unknown", "artifact has invalid value"),
    ],
)
def test_reviewer_rejects_invalid_candidate_citation_fields(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    payload = issue_payload()
    candidate_citation(payload)[field] = value

    with pytest.raises(LogicReviewError, match=message):
        reviewer(tmp_path, payload)

def test_reviewer_rejects_citation_outside_declared_scene(tmp_path: Path) -> None:
    payload = issue_payload()
    citation = candidate_citation(payload)
    citation["line_start"] = 1
    citation["line_end"] = 1
    citation["excerpt"] = "from manim import *"

    with pytest.raises(LogicReviewError, match="outside its Scene"):
        reviewer(tmp_path, payload)

def test_reviewer_rejects_missing_or_malformed_citation_sources(tmp_path: Path) -> None:
    payload = issue_payload()
    candidate_citation(payload)["unexpected"] = "field"
    with pytest.raises(LogicReviewError, match="fields do not match"):
        reviewer(tmp_path, payload)

    candidate, manifest, evidence = setup_evidence(tmp_path, expected_answer=None)
    backend = PayloadBackend(issue_payload())
    with pytest.raises(
        LogicReviewError, match="expected_answer citation has no source"
    ):
        service(backend).review(
            run_id="review-no-expected",
            evidence=evidence,
            workspace=tmp_path,
            candidate_path=candidate,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("report_extra", "review output fields do not match"),
        ("issues_not_array", "issues must be an array"),
        ("issue_not_object", "issue must be an object"),
        ("unknown_scene", "unknown Scene"),
        ("expected_not_string", "expected must be a string"),
        ("blocked_not_bool", "blocked must be bool"),
        ("confidence_not_number", "confidence must be a number"),
        ("severity_not_string", "severity must be a string"),
        ("severity_unknown", "severity has invalid value"),
    ],
)
def test_reviewer_rejects_malformed_structured_issue_fields(
    tmp_path: Path, case: str, message: str
) -> None:
    payload = issue_payload()
    issue = issue_entry(payload)
    if case == "report_extra":
        payload["unexpected"] = True
    elif case == "issues_not_array":
        payload["issues"] = "invalid"
    elif case == "issue_not_object":
        payload["issues"] = ["invalid"]
    elif case == "unknown_scene":
        issue["target_scene_ids"] = ["UnknownScene"]
    elif case == "expected_not_string":
        issue["expected"] = 10
    elif case == "blocked_not_bool":
        payload["blocked"] = "true"
    elif case == "confidence_not_number":
        issue["confidence"] = True
    elif case == "severity_not_string":
        issue["severity"] = 3
    else:
        issue["severity"] = "urgent"

    with pytest.raises(LogicReviewError, match=message):
        reviewer(tmp_path, payload)

def test_reviewer_rejects_stale_candidate_before_agent_call(tmp_path: Path) -> None:
    candidate, manifest, evidence = setup_evidence(tmp_path)
    candidate.write_text(CODE.replace("x=12", "x=11"), encoding="utf-8")
    backend = PayloadBackend(issue_payload())
    reviewer_service = service(backend)

    with pytest.raises(LogicReviewError, match="no longer matches"):
        reviewer_service.review(
            run_id="review-1",
            evidence=evidence,
            workspace=tmp_path,
            candidate_path=candidate,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

    assert backend.requests == []

def test_reviewer_fails_closed_on_non_utf8_candidate(tmp_path: Path) -> None:
    candidate, manifest, evidence = setup_evidence(tmp_path)
    candidate.write_bytes(b"\xff\xfe")
    backend = PayloadBackend(issue_payload())
    reviewer_service = service(backend)

    with pytest.raises(LogicReviewError, match="unable to read review artifact"):
        reviewer_service.review(
            run_id="review-1",
            evidence=evidence,
            workspace=tmp_path,
            candidate_path=candidate,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

    assert backend.requests == []

def test_reviewer_rejects_invalid_runtime_profile_and_evidence(tmp_path: Path) -> None:
    backend = PayloadBackend(issue_payload())
    runtime = AgentRuntime(backend, MemorySink(), limits())
    profile = reviewer_profile(model="fake-model", prompt_version="logic-v1")

    with pytest.raises(TypeError, match="runtime"):
        LogicReviewer(runtime=object(), profile=profile)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="profile"):
        LogicReviewer(runtime=runtime, profile=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="read-only reviewer"):
        LogicReviewer(
            runtime=runtime,
            profile=coder_profile(model="fake-model", prompt_version="logic-v1"),
        )

    candidate, manifest, _ = setup_evidence(tmp_path)
    with pytest.raises(TypeError, match="evidence"):
        service(backend).review(
            run_id="review-1",
            evidence=object(),  # type: ignore[arg-type]
            workspace=tmp_path,
            candidate_path=candidate,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

def test_reviewer_rejects_stale_or_non_utf8_render_manifest(tmp_path: Path) -> None:
    candidate, manifest, evidence = setup_evidence(tmp_path)
    backend = PayloadBackend(issue_payload())
    reviewer_service = service(backend)

    manifest.write_text('{"status":"stale"}', encoding="utf-8")
    with pytest.raises(LogicReviewError, match="manifest no longer matches"):
        reviewer_service.review(
            run_id="review-stale",
            evidence=evidence,
            workspace=tmp_path,
            candidate_path=candidate,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

    invalid_manifest = b"\xff\xfe"
    manifest.write_bytes(invalid_manifest)
    invalid_evidence = replace(
        evidence, render_manifest_hash=evidence_hash(invalid_manifest)
    )
    with pytest.raises(LogicReviewError, match="manifest must be UTF-8"):
        reviewer_service.review(
            run_id="review-invalid-encoding",
            evidence=invalid_evidence,
            workspace=tmp_path,
            candidate_path=candidate,
            render_manifest_path=manifest,
            estimated_input_tokens=500,
            reserved_output_tokens=300,
        )

    assert backend.requests == []
