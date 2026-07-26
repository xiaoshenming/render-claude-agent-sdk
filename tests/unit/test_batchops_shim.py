import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_existing_code_e2e as shim  # noqa: E402


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


def test_proposed_translates_to_deliver_contract(tmp_path: Path) -> None:
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
    assert result["logic"]["status"] == "candidate_ready"
    assert (output / "candidate_final.py").read_text() == "class Solution: fixed\n"
    assert (output / "video_final.mp4").read_bytes() == b"after-video"


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


def test_failed_exits_nonzero_for_fail_open(tmp_path: Path, monkeypatch) -> None:
    args = _args(tmp_path)
    monkeypatch.setattr(shim, "_arguments", lambda argv: args)
    monkeypatch.setattr(shim, "_run_operator", lambda a, h: 2)

    assert shim.main([]) == 3
    assert not (args.output / "result.json").exists()


def test_proxy_stripping_clears_all_variants(monkeypatch) -> None:
    for name in shim._PROXY_VARIABLES:
        monkeypatch.setenv(name, "http://127.0.0.1:7897")
    shim._strip_proxies()
    import os

    assert all(name not in os.environ for name in shim._PROXY_VARIABLES)
    assert os.environ["NO_PROXY"] == "*"
