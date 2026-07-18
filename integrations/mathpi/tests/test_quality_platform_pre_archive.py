from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.quality_platform.pre_archive import (
    PreArchiveQualityRequest,
    run_pre_archive_quality_platform,
)


CODE = """from manim import *

class Solution(Scene):
    def construct(self):
        A = [0, 1, 0]
        B = [1, 0, 0]
        line_AB = Line(A, B)
        self.add(line_AB)
"""


def _request(tmp_path: Path) -> PreArchiveQualityRequest:
    return PreArchiveQualityRequest(
        job_id="01QUALITYPLATFORMTEST0001",
        candidate_code=CODE,
        scene_names=("Solution",),
        problem_text="连接 A、B 两点。",
        expected_solution="线段 AB 的端点为 A 和 B。",
        artifact_root=tmp_path,
        enabled=True,
    )


def test_enabled_platform_records_hash_bound_evidence(tmp_path: Path) -> None:
    result = run_pre_archive_quality_platform(_request(tmp_path))

    assert result.selected_code == CODE
    assert result.status == "evidence_recorded"
    assert result.fail_open_used is False
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "mathpi.pre-archive-quality.v1"
    assert manifest["input"]["candidate_code_hash"] == result.selected_code_hash
    assert manifest["output"]["selected_code_hash"] == result.selected_code_hash
    assert manifest["platform"]["source_head"] == (
        "18a94aed86047f2069eb1b9d277cbfdf2e1f8980"
    )
    assert manifest["evidence"]["symbolic_scene_count"] == 1


def test_enabled_platform_records_sdk_reviewer_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "app.quality_platform.pre_archive.run_sdk_logic_review",
        lambda **_: {"decision": "pass", "issues": [], "summary": "ok"},
    )

    result = run_pre_archive_quality_platform(_request(tmp_path))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.status == "review_recorded"
    assert manifest["review"]["decision"] == "pass"
    assert manifest["platform"]["mode"] == "pre_archive_sdk_review_fail_open"
    retention = manifest["retention"]
    assert retention == {
        "model": "gemini-3.5-flash-high",
        "status": "review_recorded",
        "decision": "pass",
        "summary": "ok",
        "issues": [],
        "candidate_code_hash": result.selected_code_hash,
        "selected_code_hash": result.selected_code_hash,
        "fail_open": False,
        "error": "",
    }
    serialized = json.dumps(retention).lower()
    assert "api_key" not in serialized
    assert "token" not in serialized
    assert "base_url" not in serialized


def test_sdk_reviewer_failure_is_fail_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**_: object) -> dict[str, object]:
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(
        "app.quality_platform.pre_archive.run_sdk_logic_review", fail
    )

    result = run_pre_archive_quality_platform(_request(tmp_path))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert result.selected_code == CODE
    assert result.status == "fail_open"
    assert manifest["output"]["archive_allowed"] is True
    assert manifest["retention"]["status"] == "fail_open"
    assert manifest["retention"]["fail_open"] is True
    assert manifest["retention"]["error"] == "RuntimeError: provider unavailable"


def test_sdk_reviewer_error_redacts_provider_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-malicious-secret-value"
    base_url = "https://provider.example.com/anthropic/v1"

    def fail(**_: object) -> dict[str, object]:
        raise RuntimeError(
            f"POST {base_url} Authorization: Bearer {secret} "
            f"api_key={secret} token={secret}"
        )

    monkeypatch.setattr(
        "app.quality_platform.pre_archive.run_sdk_logic_review", fail
    )
    monkeypatch.setattr(
        "app.quality_platform.retention.settings.MANIM_QUALITY_ANTHROPIC_API_KEY",
        secret,
    )
    monkeypatch.setattr(
        "app.quality_platform.retention.settings.MANIM_QUALITY_ANTHROPIC_BASE_URL",
        base_url,
    )

    result = run_pre_archive_quality_platform(_request(tmp_path))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    error = manifest["retention"]["error"]
    assert secret not in error
    assert base_url not in error
    assert "provider.example.com" not in error
    assert "Bearer" not in error
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert secret not in serialized
    assert base_url not in serialized
    assert "Bearer" not in serialized


def test_sdk_reviewer_output_redacts_echoed_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-reviewer-echo-secret"
    url = "https://secret.example.com/v1/messages"
    monkeypatch.setattr(
        "app.quality_platform.pre_archive.run_sdk_logic_review",
        lambda **_: {
            "decision": "needs_repair",
            "summary": f"POST {url} Authorization: Bearer {secret}",
            "issues": [
                {
                    "scene": f"token={secret}",
                    "issue": f"api_key={secret}",
                    "evidence": f"request={url} Bearer {secret}",
                }
            ],
        },
    )

    result = run_pre_archive_quality_platform(_request(tmp_path))

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert secret not in serialized
    assert url not in serialized
    assert "secret.example.com" not in serialized
    assert "Bearer" not in serialized


def test_platform_failure_keeps_renderable_code_and_records_error(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request = replace(request, scene_names=("MissingScene",))

    result = run_pre_archive_quality_platform(request)

    assert result.selected_code == CODE
    assert result.status == "fail_open"
    assert result.fail_open_used is True
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["output"]["archive_allowed"] is True
    assert manifest["output"]["error_type"] == "ValueError"


def test_disabled_platform_preserves_legacy_code_without_artifacts(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    request = replace(request, enabled=False)

    result = run_pre_archive_quality_platform(request)

    assert result.selected_code == CODE
    assert result.status == "disabled"
    assert result.manifest_path is None


def test_empty_candidate_is_rejected_before_archive(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request = replace(request, candidate_code="  ")

    with pytest.raises(ValueError, match="candidate_code"):
        run_pre_archive_quality_platform(request)


def test_repeated_attempts_use_distinct_manifest_directories(tmp_path: Path) -> None:
    first = run_pre_archive_quality_platform(_request(tmp_path))
    second = run_pre_archive_quality_platform(_request(tmp_path))

    assert first.manifest_path != second.manifest_path
    assert first.manifest_path.is_file()
    assert second.manifest_path.is_file()
