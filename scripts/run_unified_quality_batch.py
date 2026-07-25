"""Run the unified Quality Operator over a frozen case directory."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def main() -> int:
    args = _arguments()
    cases = sorted(args.package.glob("cases/*/source/main.py"))
    if not cases:
        raise SystemExit("no cases/*/source/main.py files found")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "_batch_logs").mkdir(exist_ok=True)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(_run_case, args, candidate): candidate
            for candidate in cases
        }
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(
                f"[{len(results)}/{len(cases)}] {result['case_id']}: "
                f"{result['status']}",
                flush=True,
            )
    results.sort(key=lambda item: str(item["case_id"]))
    summary = _summary(results, round(time.monotonic() - started, 3))
    (args.output / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["totals"], ensure_ascii=False), flush=True)
    return 0 if summary["totals"]["failed"] == 0 else 1


def _run_case(args, candidate: Path) -> dict[str, object]:
    case_dir = candidate.parents[1]
    case_id = case_dir.name
    output = args.output / case_id
    log_root = args.output / "_batch_logs"
    decision_path = output / "output" / "decision.json"
    if decision_path.is_file():
        return _result(case_id, output, 0, 0.0, resumed=True)
    output.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-m",
        "manim_quality.operator",
        "--candidate",
        str(candidate),
        "--workspace",
        str(candidate.parent),
        "--output",
        str(output),
        "--model",
        args.model,
        "--manim-python",
        str(args.manim_python),
        "--runtime-python-path",
        str(args.runtime_python_path),
        "--assets-dir",
        str(case_dir / "assets"),
        "--max-turns",
        str(args.max_turns),
        "--max-tool-calls",
        str(args.max_tool_calls),
        "--estimated-input-tokens",
        "5000",
        "--reserved-output-tokens",
        "2500",
    ]
    started = time.monotonic()
    with (log_root / f"{case_id}.stdout.log").open(
        "w", encoding="utf-8"
    ) as stdout:
        with (log_root / f"{case_id}.stderr.log").open(
            "w", encoding="utf-8"
        ) as stderr:
            try:
                completed = subprocess.run(
                    argv,
                    cwd=args.repo,
                    env=os.environ.copy(),
                    stdout=stdout,
                    stderr=stderr,
                    timeout=args.case_timeout,
                    check=False,
                    shell=False,
                )
                exit_code = completed.returncode
            except subprocess.TimeoutExpired:
                exit_code = 124
    elapsed = round(time.monotonic() - started, 3)
    return _result(case_id, output, exit_code, elapsed, resumed=False)


def _result(
    case_id: str,
    output: Path,
    exit_code: int,
    elapsed: float,
    *,
    resumed: bool,
) -> dict[str, object]:
    decision_path = output / "output" / "decision.json"
    decision = _read_json(decision_path)
    status = str(decision.get("decision") or "FAILED")
    return {
        "case_id": case_id,
        "status": status,
        "exit_code": exit_code,
        "elapsed_seconds": elapsed,
        "resumed": resumed,
        "decision": decision,
        "output": str(output),
    }


def _summary(
    results: list[dict[str, object]],
    elapsed: float,
) -> dict[str, object]:
    proposed = sum(item["status"] == "PROPOSED" for item in results)
    hold = sum(item["status"] == "HOLD" for item in results)
    failed = len(results) - proposed - hold
    tokens = sum(
        int(dict(dict(item["decision"]).get("tokens") or {}).get("total_tokens") or 0)
        for item in results
    )
    return {
        "totals": {
            "cases": len(results),
            "proposed": proposed,
            "hold": hold,
            "failed": failed,
            "proposed_rate": proposed / len(results),
            "tokens": tokens,
            "elapsed_seconds": elapsed,
        },
        "results": results,
    }


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument("--runtime-python-path", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--case-timeout", type=int, default=900)
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument("--max-tool-calls", type=int, default=18)
    args = parser.parse_args()
    for name in ("concurrency", "case_timeout", "max_turns", "max_tool_calls"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
