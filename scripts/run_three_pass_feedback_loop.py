#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from manim_quality.feedback_loop.models import Candidate, LoopExecutionIdentity
from manim_quality.feedback_loop.runner import FeedbackLoopRunner
from manim_quality.feedback_loop.store import JsonLoopStore
from manim_quality.feedback_loop.subprocess_ports import (
    ProcessConfig,
    SubprocessAssurance,
    SubprocessCoder,
)


def main() -> int:
    args = arguments()
    args.output.mkdir(parents=True, exist_ok=True)
    config = ProcessConfig(
        repo=args.repo.resolve(),
        root=args.output.resolve(),
        case_id=args.case_id,
        question=args.question,
        assets_dir=args.assets_dir,
        model=args.model,
        manim_python=args.manim_python,
        runtime_python_paths=tuple(args.runtime_python_path),
        max_turns=args.max_turns,
        max_tool_calls=args.max_tool_calls,
        tts_mode=args.tts_mode,
    )
    coder = SubprocessCoder(config)
    generated = Candidate(
        revision_id="generated-R0",
        source_sha256=sha256(args.source),
        video_sha256=sha256(args.video),
        source_path=str(args.source.resolve()),
        video_path=str(args.video.resolve()),
    )
    identity = execution_identity(args, generated)
    runner = FeedbackLoopRunner(
        coder=coder,
        assurance=SubprocessAssurance(config),
        store=JsonLoopStore(args.output / "loop-state.json"),
        tts_mode=args.tts_mode,
    )
    result = runner.run(
        generated,
        identity=identity,
        bootstrap=True,
        resume=args.resume,
    )
    payload = asdict(result)
    (args.output / "loop-result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "case_id": args.case_id,
        "grade": result.final_grade,
        "assurance_passes": result.assurance_passes,
        "repair_rounds": result.repair_rounds,
        "terminal_reason": result.terminal_reason,
    }, ensure_ascii=False))
    return 0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--question", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument(
        "--runtime-python-path", action="append", type=Path, required=True
    )
    parser.add_argument(
        "--tts-mode", choices=("disabled", "required"), default="disabled"
    )
    parser.add_argument("--max-turns", type=int, default=24)
    parser.add_argument("--max-tool-calls", type=int, default=40)
    parser.add_argument("--prompt-version", default="quality-operator-v3")
    parser.add_argument("--tool-version", default="quality-tools-v2")
    parser.add_argument("--policy-version", default="feedback-loop-v2")
    parser.add_argument("--runtime-version", default="claude-agent-sdk")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def execution_identity(args, generated: Candidate) -> LoopExecutionIdentity:
    return LoopExecutionIdentity(
        job_id=args.case_id,
        question_sha256=text_sha256(args.question),
        source_sha256=generated.source_sha256,
        video_sha256=generated.video_sha256,
        model_id=args.model,
        prompt_version=args.prompt_version,
        tool_version=args.tool_version,
        policy_version=args.policy_version,
        runtime_version=args.runtime_version,
        schema_version="feedback-loop-v2",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
