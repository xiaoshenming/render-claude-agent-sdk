"""Replay a frozen historical logic library through the current V3 logic stage."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT / "src", ROOT, ROOT / "vendor/logic_engine_mvp_baseline"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from evals.workbench_e2e.logic_stage import LogicStageConfig, run_logic_stage
from manim_quality.logic.review_input import ReviewInputVersion


def main() -> int:
    args = _arguments()
    cases = [path for path in sorted(args.library.iterdir()) if _complete(path)]
    args.output.mkdir(parents=True, exist_ok=True)
    args.work_root.mkdir(parents=True, exist_ok=True)
    results = _run_all(cases, args)
    _write_json(args.output / "results.json", results)
    _write_csv(args.output / "results.csv", results)
    _write_json(args.output / "summary.json", _summary(results))
    print(json.dumps(_summary(results), ensure_ascii=False, indent=2))
    return 0


def _run_all(cases: list[Path], args) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(_run_one, case, args): case for case in cases}
        for index, future in enumerate(as_completed(futures), 1):
            case = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {
                    "job_id": case.name,
                    "status": "runner_error",
                    "error": f"{type(error).__name__}: {error}"[:2000],
                }
            results.append(result)
            print(
                json.dumps(
                    {"done": index, "total": len(cases), **result},
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return sorted(results, key=lambda item: str(item["job_id"]))


def _run_one(case: Path, args) -> dict[str, object]:
    job_id = case.name
    existing = _read_json(args.work_root / job_id / "logic_summary.json")
    if existing:
        return _enrich_result(job_id, existing, args.work_root / job_id)
    planning = _planning(case)
    result = run_logic_stage(
        job_id=job_id,
        candidate=case / "baseline.py",
        problem=(case / "problem.txt").read_text(encoding="utf-8"),
        expected_solution=(case / "expected.txt").read_text(encoding="utf-8"),
        planning=planning,
        baseline_video=case / "baseline.mp4",
        output_dir=args.work_root / job_id,
        config=LogicStageConfig(
            model=os.environ["MANIM_QUALITY_MODEL"],
            provider_env=_provider(),
            input_version=ReviewInputVersion(args.input_version),
            runtime_python=str(args.manim_python),
            probe_source=args.probe_source,
            repair_enabled=not args.review_only,
        ),
    )
    payload = {**asdict(result), "candidate_path": str(result.candidate_path)}
    return _enrich_result(job_id, payload, args.work_root / job_id)


def _enrich_result(job_id: str, payload: dict, root: Path) -> dict[str, object]:
    relation = _read_json(root / "dataset/expected_actual_relations.cache.json")
    snapshots = list(
        root.glob(
            "review/attempt-*/cases/*/runtime_geometry/runtime_geometry_snapshot.json"
        )
    )
    return {
        "job_id": job_id,
        **payload,
        "review_attempts": len(list((root / "review").glob("attempt-*"))),
        "relation_status": relation.get("status"),
        "relation_claims": len((relation.get("contract") or {}).get("claims") or []),
        "runtime_final": bool(snapshots),
    }


def _planning(case: Path) -> dict[str, object]:
    return {
        "scene_intent": (case / "problem.txt").read_text(encoding="utf-8"),
    }


def _provider() -> dict[str, str]:
    key = os.environ["MANIM_QUALITY_ANTHROPIC_API_KEY"]
    return {
        "ANTHROPIC_BASE_URL": os.environ["MANIM_QUALITY_ANTHROPIC_BASE_URL"],
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_API_KEY": key,
    }


def _complete(path: Path) -> bool:
    names = ("baseline.py", "baseline.mp4", "problem.txt", "expected.txt")
    return path.is_dir() and all((path / name).is_file() for name in names)


def _summary(results: list[dict[str, object]]) -> dict[str, object]:
    statuses: dict[str, int] = {}
    for item in results:
        status = str(item.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "attempted": len(results),
        "statuses": statuses,
        "protocol_retried": sum(int(item.get("review_attempts") or 0) > 1 for item in results),
        "expected_actual_available": sum(item.get("relation_status") == "available" for item in results),
        "runtime_final_available": sum(item.get("runtime_final") is True for item in results),
        "review_tokens": sum(int(item.get("review_tokens") or 0) for item in results),
        "repair_tokens": sum(int(item.get("repair_tokens") or 0) for item in results),
        "review_elapsed_ms": sum(int(item.get("review_elapsed_ms") or 0) for item in results),
        "repair_elapsed_ms": sum(int(item.get("repair_elapsed_ms") or 0) for item in results),
    }


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--manim-python", type=Path, required=True)
    parser.add_argument("--probe-source", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument(
        "--input-version",
        choices=tuple(item.value for item in ReviewInputVersion),
        default=ReviewInputVersion.DIGEST_V2_2_GEOMETRY.value,
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
