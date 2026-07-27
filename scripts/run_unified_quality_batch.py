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

from batch_runtime import preflight, write_manifest


def main() -> int:
    args = _arguments()
    cases = sorted(args.package.glob("cases/*/source/main.py"))
    if not cases:
        raise SystemExit("no cases/*/source/main.py files found")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "_batch_logs").mkdir(exist_ok=True)
    manifest = preflight(args, cases)
    write_manifest(args.output / "runtime_manifest.json", manifest)
    if manifest["status"] != "ok":
        print(json.dumps(manifest, ensure_ascii=False, indent=2), file=sys.stderr)
        return 3
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.agent_concurrency) as pool:
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
    results = _retry_transient_failures(args, cases, results)
    results.sort(key=lambda item: str(item["case_id"]))
    summary = _summary(results, round(time.monotonic() - started, 3))
    (args.output / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["totals"], ensure_ascii=False), flush=True)
    return 0 if summary["totals"]["failed"] == 0 else 1


_TRANSIENT_MARKERS = (
    "econnreset",
    "server_error",
    "unable to connect",
    "connection error",
    "overloaded",
)


def _transient_infra_failure(result: dict[str, object]) -> bool:
    if result.get("status") != "FAILED":
        return False
    decision = result.get("decision")
    error = str((decision or {}).get("error", "")).lower()
    return any(marker in error for marker in _TRANSIENT_MARKERS)


def _retry_transient_failures(args, cases, results):
    """Retry gateway-level failures once; the first attempt is kept aside."""

    by_id = {candidate.parents[1].name: candidate for candidate in cases}
    updated = []
    for result in results:
        case_id = str(result["case_id"])
        failed_dir = args.output / case_id
        attempt_dir = args.output / f"{case_id}.infra_failed_1"
        if (
            not _transient_infra_failure(result)
            or case_id not in by_id
            or attempt_dir.exists()
        ):
            updated.append(result)
            continue
        failed_dir.rename(attempt_dir)
        print(f"[retry] {case_id}: transient infra failure, one retry", flush=True)
        retried = _run_case(args, by_id[case_id])
        retried["infra_retried"] = True
        updated.append(retried)
    return updated


def _run_case(args, candidate: Path) -> dict[str, object]:
    case_dir = candidate.parents[1]
    case_id = case_dir.name
    output = args.output / case_id
    log_root = args.output / "_batch_logs"
    decision_path = output / "output" / "decision.json"
    if decision_path.is_file():
        return _result(case_id, output, 0, 0.0, resumed=True)
    print(f"[start] {case_id}", flush=True)
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
    if args.allow_ambient_login:
        argv.append("--allow-ambient-login")
    if args.render_cache:
        argv.append("--render-cache")
    started = time.monotonic()
    with (log_root / f"{case_id}.stdout.log").open(
        "w", encoding="utf-8"
    ) as stdout:
        with (log_root / f"{case_id}.stderr.log").open(
            "w", encoding="utf-8"
        ) as stderr:
            exit_code = _run_bounded_case(
                argv,
                args=args,
                stdout=stdout,
                stderr=stderr,
            )
    elapsed = round(time.monotonic() - started, 3)
    return _result(case_id, output, exit_code, elapsed, resumed=False)


def _run_bounded_case(argv, *, args, stdout, stderr) -> int:
    """Bound one case; on timeout SIGTERM first so the CLI can persist
    failure evidence, and only SIGKILL after the grace period."""

    process = subprocess.Popen(
        argv,
        cwd=args.repo,
        env=_case_environment(args),
        stdout=stdout,
        stderr=stderr,
        shell=False,
    )
    try:
        return process.wait(timeout=args.case_timeout)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=args.case_grace)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return 124


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


def _case_environment(args) -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str((args.repo / "src").resolve())
    inherited = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = (
        source_root if not inherited else os.pathsep.join((source_root, inherited))
    )
    environment["MANIM_RENDER_CONCURRENCY"] = str(args.render_concurrency)
    environment.setdefault(
        "MANIM_RENDER_SEMAPHORE_DIR",
        str((args.output / "_render_slots").resolve()),
    )
    return environment


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument("--runtime-python-path", type=Path, required=True)
    parser.add_argument("--agent-concurrency", type=int, default=20)
    parser.add_argument("--render-concurrency", type=int, default=10)
    parser.add_argument("--case-timeout", type=int, default=3_600)
    parser.add_argument("--case-grace", type=int, default=120)
    parser.add_argument("--allow-ambient-login", action="store_true")
    parser.add_argument("--render-cache", action="store_true")
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument("--max-tool-calls", type=int, default=16)
    args = parser.parse_args()
    for name in (
        "agent_concurrency",
        "render_concurrency",
        "case_timeout",
        "case_grace",
        "max_turns",
        "max_tool_calls",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
