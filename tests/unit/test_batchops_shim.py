import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_existing_code_e2e as shim  # noqa: E402
from batchops_result_contract import token_usage  # noqa: E402


def _decision(harness: Path, payload: dict) -> None:
    (harness / "output").mkdir(parents=True, exist_ok=True)
    (harness / "output" / "decision.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _args(tmp_path: Path):
    code = tmp_path / "workspace" / "candidate.py"
    code.parent.mkdir(parents=True, exist_ok=True)
    code.write_text("class Solution: pass\n", encoding="utf-8")
    baseline = tmp_path / "baseline.mp4"
    baseline.write_bytes(b"before-video")
    return shim._arguments(
        [
            "--code",
            str(code),
            "--problem",
            str(code),
            "--baseline-video",
            str(baseline),
            "--manim-python",
            str(code),
            "--output",
            str(tmp_path / "run"),
            "--job-id",
            "attempt-1",
            "--model",
            "test-model",
        ]
    )


def test_proposed_is_candidate_ready_for_assurance(tmp_path: Path) -> None:
    args = _args(tmp_path)
    output = args.output
    harness = output / "harness"
    _decision(
        harness,
        {
            "decision": "PROPOSED",
            "final_revision_id": "R2",
            "turns": 13,
            "tokens": {"total_tokens": 69101},
            "reviewer_tokens": 900,
            "total_tokens_with_reviewers": 70001,
            "usage_complete": False,
        },
    )
    (harness / "output" / "proposed_candidate.py").write_text(
        "class Solution: fixed\n", encoding="utf-8"
    )
    video_dir = harness / "acceptance_runtime" / "R2" / "media"
    video_dir.mkdir(parents=True)
    (video_dir / "final.mp4").write_bytes(b"after-video")
    output.mkdir(parents=True, exist_ok=True)

    code = shim._emit_proposed(args, output, harness, shim._read_decision(harness))

    assert code == 0
    result = json.loads((output / "result.json").read_text())
    assert result["status"] == "deliver"
    assert result["agent_outcome"]["status"] == "candidate_ready_for_assurance"
    assert result["delivery_authorized"] is False
    assert result["logic"]["status"] == "candidate_ready"
    assert result["token_usage"]["total_tokens"] == 70001
    assert result["token_usage"]["entries"] == [
        {"operation": "parent", "total_tokens": 69101},
        {"operation": "reviewers", "total_tokens": 900},
    ]
    assert result["token_usage"]["complete"] is False
    assert result["token_usage"]["missing_operations"] == ["parent"]
    assert (output / "candidate_final.py").read_text() == "class Solution: fixed\n"
    assert (output / "video_final.mp4").read_bytes() == b"after-video"
    assert result["artifact_identity"]["revision_id"] == "R2"
    assert result["artifact_identity"]["manifest_sha256"]


def test_proposed_reuses_verified_video_from_shared_render_cache(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path)
    output = args.output
    harness = output / "harness"
    cache = tmp_path / "manim-cache"
    video = cache / "videos/480p15/Solution.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"cached-r1-video")
    args.render_cache_dir = cache
    decision = {
        "decision": "PROPOSED",
        "final_revision_id": "R1",
        "validation": {"details": {"video_path": str(video)}},
    }
    _decision(harness, decision)
    (harness / "output" / "proposed_candidate.py").write_text(
        "class Solution: fixed\n", encoding="utf-8"
    )
    output.mkdir(parents=True, exist_ok=True)

    code = shim._emit_proposed(args, output, harness, decision)

    assert code == 0
    assert (output / "video_final.mp4").read_bytes() == b"cached-r1-video"


def test_proposed_rejects_reported_video_outside_shared_cache(
    tmp_path: Path,
) -> None:
    args = _args(tmp_path)
    output = args.output
    harness = output / "harness"
    cache = tmp_path / "manim-cache"
    cache.mkdir()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"untrusted-video")
    args.render_cache_dir = cache
    decision = {
        "decision": "PROPOSED",
        "final_revision_id": "R1",
        "validation": {"details": {"video_path": str(outside)}},
    }
    _decision(harness, decision)
    (harness / "output" / "proposed_candidate.py").write_text(
        "class Solution: fixed\n", encoding="utf-8"
    )
    output.mkdir(parents=True, exist_ok=True)

    code = shim._emit_proposed(args, output, harness, decision)

    assert code == 3
    assert not (output / "video_final.mp4").exists()


def test_agent_tree_usage_does_not_double_count_reviewers(tmp_path: Path) -> None:
    decision = {
        "tokens": {"total_tokens": 55_842},
        "tokens_scope": "agent_tree",
        "reviewer_tokens": 4_659,
        "reviewer_tokens_included": True,
        "total_tokens_with_reviewers": 55_842,
        "usage_complete": True,
    }

    usage = token_usage(decision)

    assert usage["total_tokens"] == 55_842
    assert usage["entries"] == [
        {"operation": "quality_agent", "total_tokens": 55_842}
    ]
    assert usage["reviewer_attribution_tokens"] == 4_659
    assert usage["missing_operations"] == []


def test_hold_delivers_untouched_before_with_warning(tmp_path: Path) -> None:
    args = _args(tmp_path)
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    decision = {
        "decision": "HOLD",
        "reasons": ["missing_agent_submission"],
        "best_render_passed": {"revision_id": "R3", "blocking_count": 1},
    }

    code = shim._emit_hold(args, output, decision)

    assert code == 0
    result = json.loads((output / "result.json").read_text())
    assert result["status"] == "deliver_with_warning"
    assert result["layout"]["risk_codes"] == ["quality_hold_before_retained"]
    assert (
        (output / "candidate_final.py").read_bytes()
        == args.code.read_bytes()
    )
    assert (output / "video_final.mp4").read_bytes() == b"before-video"
    assert result["artifact_identity"]["revision_id"] == "R0"
    assert result["artifact_identity"]["source_revision_id"] == "R0"
    assert result["artifact_identity"]["video_revision_id"] == "R0"


def test_operator_edits_session_copy_not_caller_source(
    tmp_path: Path, monkeypatch
) -> None:
    args = _args(tmp_path)
    original = args.code.read_text(encoding="utf-8")
    captured = {}

    def fake_main(argv):
        candidate = Path(argv[argv.index("--candidate") + 1])
        captured["candidate"] = candidate
        candidate.write_text("class Solution: changed\n", encoding="utf-8")
        return 0

    monkeypatch.setattr("manim_quality.operator.cli.main", fake_main)

    assert shim._run_operator(args, tmp_path / "harness") == 0
    assert captured["candidate"] != args.code
    assert args.code.read_text(encoding="utf-8") == original


def test_failed_exits_nonzero_for_fail_open(tmp_path: Path, monkeypatch) -> None:
    args = _args(tmp_path)
    monkeypatch.setattr(shim, "_arguments", lambda argv: args)
    monkeypatch.setattr(shim, "_run_operator", lambda a, h: 2)

    assert shim.main([]) == 3
    result = json.loads((args.output / "result.json").read_text())
    assert result["status"] == "failed"
    assert result["agent_outcome"]["status"] == "failed"


def test_proxy_stripping_clears_all_variants(monkeypatch) -> None:
    for name in shim._PROXY_VARIABLES:
        monkeypatch.setenv(name, "http://127.0.0.1:7897")
    shim._strip_proxies()
    import os

    assert all(name not in os.environ for name in shim._PROXY_VARIABLES)
    assert os.environ["NO_PROXY"] == "*"


def test_runtime_python_paths_are_forwarded(tmp_path: Path, monkeypatch) -> None:
    args = _args(tmp_path)
    runtime = tmp_path / "render-runtime"
    runtime.mkdir()
    args.runtime_python_path = [runtime]
    captured = {}

    def fake_main(argv):
        captured["argv"] = argv
        return 0

    monkeypatch.setattr("manim_quality.operator.cli.main", fake_main)

    assert shim._run_operator(args, tmp_path / "harness") == 0
    index = captured["argv"].index("--runtime-python-path")
    assert captured["argv"][index + 1] == str(runtime.resolve())
