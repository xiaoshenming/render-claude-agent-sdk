from copy import deepcopy
from pathlib import Path

import pytest
from _reviewer_support import (
    CODE,
    add_citation,
    issue_payload,
    reviewer,
)
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from test_review_input_versions import geometry_snapshot

from manim_quality.logic.output_schema import REVIEW_OUTPUT_SCHEMA
from manim_quality.logic.review_input import ReviewInputVersion
from manim_quality.logic.schemas import LogicDecision
from manim_quality.revisions.fingerprint import code_hash


def test_reviewer_returns_platform_bound_direct_evidence(tmp_path: Path) -> None:
    result, backend, sink = reviewer(tmp_path, issue_payload())

    assert result.report.decision is LogicDecision.NEEDS_REPAIR
    assert result.report.revision_id == "rev-1"
    assert result.report.issues[0].evidence[0].source_hash == code_hash(CODE)
    assert result.call_record == sink.records[0]
    request = backend.requests[0]
    assert request.allowed_tools == ("Read",)
    assert request.output_schema["additionalProperties"] is False
    issue_schema = request.output_schema["properties"]["issues"]["items"]
    assert issue_schema["properties"]["expected"]["minLength"] == 1
    assert issue_schema["properties"]["observed"]["minLength"] == 1
    assert CODE not in request.prompt
    assert "job-1" not in request.prompt
    assert "rev-1" not in request.prompt
    assert "sha256:" not in request.prompt
    assert '"input_version"' not in request.prompt
    assert "layout overlap" in request.prompt
    assert "computed evidence candidates, not repair instructions" in request.prompt
    assert (
        "cite problem, planning, or expected answer as the expected claim source"
        in request.prompt
    )
    assert (
        "verify them against candidate.py before reporting an issue" in request.prompt
    )
    assert (
        "Repairable issues require at least one concrete acceptance predicate"
        in request.prompt
    )
    assert (
        "expected and observed must be non-empty and genuinely different"
        in request.prompt
    )


def test_digest_v2_is_explicit_and_versioned(tmp_path: Path) -> None:
    result, backend, _ = reviewer(
        tmp_path,
        issue_payload(),
        input_version=ReviewInputVersion.DIGEST_V2,
    )

    request = backend.requests[0]
    assert result.report.decision is LogicDecision.NEEDS_REPAIR
    assert '"input_version":"digest-v2"' in request.prompt
    assert "focused_code_excerpts" not in request.prompt
    assert "helper_method_excerpts" not in request.prompt


def test_geometry_reviewer_binds_one_readonly_tool_without_changing_builtins(
    tmp_path: Path,
) -> None:
    result, backend, _ = reviewer(
        tmp_path,
        issue_payload(),
        input_version=ReviewInputVersion.DIGEST_V2_2_GEOMETRY,
        geometry_snapshot=geometry_snapshot(),
    )

    request = backend.requests[0]
    assert result.report.decision is LogicDecision.NEEDS_REPAIR
    assert request.allowed_tools == ("Read",)
    assert len(request.read_tools) == 1
    assert (
        request.read_tools[0].sdk_name
        == "mcp__geometry__inspect_geometry_relation"
    )


def test_geometry_reviewer_requires_current_code_bound_snapshot(tmp_path: Path) -> None:
    stale = geometry_snapshot()
    object.__setattr__(stale, "code_hash", "sha256:" + "f" * 64)

    with pytest.raises(ValueError, match="geometry snapshot"):
        reviewer(
            tmp_path,
            issue_payload(),
            input_version=ReviewInputVersion.DIGEST_V2_2_GEOMETRY,
            geometry_snapshot=stale,
        )


def test_reviewer_accepts_clean_probe_without_inventing_issues(tmp_path: Path) -> None:
    payload = {
        "decision": "pass",
        "blocked": False,
        "requires_human_review": False,
        "summary": "未发现有直接证据支持的逻辑错误",
        "review_gaps": [],
        "issues": [],
    }

    result, _, _ = reviewer(tmp_path, payload)

    assert result.report.decision is LogicDecision.PASS
    assert result.report.issues == ()


@pytest.mark.parametrize(
    ("artifact", "excerpt"),
    [
        ("problem_text", "解方程 x+2=12。"),
        ("planning", "两边减 2"),
        ("render_manifest", "rendered"),
    ],
)
def test_reviewer_binds_non_code_citations_to_platform_sources(
    tmp_path: Path, artifact: str, excerpt: str
) -> None:
    payload = issue_payload()
    add_citation(payload, artifact=artifact, excerpt=excerpt)

    result, _, _ = reviewer(tmp_path, payload)

    bound = result.report.issues[0].evidence[-1]
    assert bound.artifact.value == artifact
    assert bound.source_hash.startswith("sha256:")


def test_reviewer_preserves_blocking_human_review_semantics(tmp_path: Path) -> None:
    payload = {
        "decision": "human_review",
        "blocked": True,
        "requires_human_review": True,
        "summary": "现有来源不足以验证几何关系",
        "review_gaps": ["缺少题目中点的定义"],
        "issues": [],
    }

    result, _, _ = reviewer(tmp_path, payload)

    assert result.report.decision is LogicDecision.HUMAN_REVIEW
    assert result.report.blocked is True


def test_output_schema_requires_candidate_and_expected_source_citations() -> None:
    valid = issue_payload()
    Draft202012Validator(REVIEW_OUTPUT_SCHEMA).validate(valid)
    missing_expected_source = deepcopy(valid)
    del missing_expected_source["issues"][0]["expected_evidence"]

    with pytest.raises(ValidationError, match="required property"):
        Draft202012Validator(REVIEW_OUTPUT_SCHEMA).validate(missing_expected_source)


def test_output_schema_rejects_code_locations_on_expected_source() -> None:
    payload = issue_payload()
    citation = payload["issues"][0]["expected_evidence"][0]
    citation["scene_id"] = "Scene_02_Solve"
    citation["line_start"] = 1
    citation["line_end"] = 1

    with pytest.raises(ValidationError):
        Draft202012Validator(REVIEW_OUTPUT_SCHEMA).validate(payload)
