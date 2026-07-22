from pathlib import Path
from types import SimpleNamespace

import pytest

from manim_quality.layout.adapter import OverlapAdapter
from manim_quality.layout.policy import ResidualRiskPolicy
from manim_quality.layout.result_mapping import OverlapDisposition

from .overlap_support import (
    BASE_CODE,
    fake_runner,
    make_check,
    make_request,
)


def test_clean_vendor_result_does_not_create_a_candidate(
    tmp_path: Path, vendor_api
) -> None:
    backend, api = vendor_api
    checker = api.StubChecker([make_check(api, 0)])

    result = OverlapAdapter(backend).repair(make_request(tmp_path), checker)

    assert result.disposition is OverlapDisposition.NO_CHANGE
    assert result.vendor_status == "REPAIR_UNCHANGED"
    assert result.requires_external_render_recheck is False
    assert result.tokens_used == 0
    assert result.evidence_dir is not None


def test_centered_shape_label_is_recorded_without_starting_agent(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api

    class ForbiddenRunner:
        def __init__(self, **kwargs):
            del kwargs
            raise AssertionError("Agent must not run for intentional containment")

    monkeypatch.setattr(api.api_module, "ClaudeSDKRunner", ForbiddenRunner)
    issue = {
        "category": "label_shape_overlap_risk",
        "a_raw": {
            "class": "Polygon",
            "kind": "shape",
            "bbox": {
                "left": -1,
                "right": 1,
                "top": 1,
                "bottom": -1,
                "width": 2,
                "height": 2,
                "center_x": 0,
                "center_y": 0,
            },
        },
        "b_raw": {
            "class": "MathTex",
            "kind": "formula",
            "text": "a^2",
            "bbox": {
                "left": -0.2,
                "right": 0.2,
                "top": 0.2,
                "bottom": -0.2,
                "width": 0.4,
                "height": 0.4,
                "center_x": 0,
                "center_y": 0,
            },
        },
    }
    checker = api.StubChecker(
        [api.CheckResult(ok=True, passed=False, blocking_count=1, issues=[issue])]
    )

    result = OverlapAdapter(backend).repair(make_request(tmp_path), checker)

    assert result.disposition is OverlapDisposition.NO_CHANGE
    assert result.before_blocking == 0
    evidence = result.evidence_dir / "workdir" / "platform_overlap_classification.json"
    assert evidence.is_file()


def test_platform_runs_at_most_five_rounds_for_must_repair(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api
    captured = {}

    def capture(bundle, toolbox):
        del toolbox
        captured["bundle"] = bundle
        captured["budget"] = bundle.budget
        return SimpleNamespace(
            status="REPAIR_UNCHANGED",
            code_path=bundle.code_path,
            repairability="auto_ready",
            before={"blocking_count": 1},
            after={"blocking_count": 1},
            rounds_used=0,
            tokens_used=0,
            cost_usd=0.0,
            evidence_dir=bundle.evidence_root,
            reasons=[],
        )

    monkeypatch.setattr(api, "repair", capture)
    backend.repair(make_request(tmp_path, tokens=400_000), object())

    assert captured["budget"].max_rounds == 5
    assert captured["budget"].no_progress_stop == 2
    assert captured["budget"].accept_degraded_max_blocking == 0
    assert captured["budget"].token_hard_cap == 2**63 - 1
    assert captured["bundle"].candidate_mode == "core"


def test_clean_repair_is_only_a_candidate_and_preserves_usage_and_evidence(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api
    edited = BASE_CODE.replace("label.move_to(ORIGIN)", "label.shift(UP)")
    monkeypatch.setattr(
        api.api_module, "ClaudeSDKRunner", lambda **_: fake_runner(api, edited)
    )
    checker = api.StubChecker(
        [make_check(api, 2), make_check(api, 0), make_check(api, 0)]
    )

    result = OverlapAdapter(backend).repair(make_request(tmp_path), checker)

    assert result.disposition is OverlapDisposition.CANDIDATE_RECHECK_REQUIRED
    assert result.requires_external_render_recheck is True
    assert result.tokens_used == 321
    assert result.rounds_used == 1
    assert result.code_path.read_text(encoding="utf-8") == edited
    assert (result.evidence_dir / "summary.json").is_file()


def test_layout_repair_keeps_candidate_and_records_semantic_risk(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api
    edited = BASE_CODE.replace("Write(label)", "Create(label)").replace(
        "label.move_to(ORIGIN)", "label.shift(UP)"
    )
    monkeypatch.setattr(
        api.api_module, "ClaudeSDKRunner", lambda **_: fake_runner(api, edited)
    )
    checker = api.StubChecker(
        [make_check(api, 2), make_check(api, 0), make_check(api, 0)]
    )

    result = OverlapAdapter(backend).repair(make_request(tmp_path), checker)

    assert result.disposition is OverlapDisposition.CANDIDATE_RECHECK_REQUIRED
    assert result.code_path != tmp_path / "candidate.py"
    assert "semantic_fingerprint_changed_risk" in result.reasons


def test_degraded_result_requires_platform_residual_risk_policy(
    tmp_path: Path, vendor_api, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend, api = vendor_api
    edited = BASE_CODE.replace("label.move_to(ORIGIN)", "label.shift(UP)")
    monkeypatch.setattr(
        api.api_module, "ClaudeSDKRunner", lambda **_: fake_runner(api, edited)
    )
    checker = api.StubChecker(
        [make_check(api, 4), make_check(api, 2), make_check(api, 2)]
    )
    policy = ResidualRiskPolicy(max_degraded_blocking=2, min_reduction_ratio=0.5)

    result = OverlapAdapter(backend, policy=policy).repair(
        make_request(tmp_path), checker
    )

    assert result.disposition is OverlapDisposition.RESIDUAL_CANDIDATE_RECHECK_REQUIRED
    assert result.requires_external_render_recheck is True
    assert result.before_blocking == 4
    assert result.after_blocking == 2
