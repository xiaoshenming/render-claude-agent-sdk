"""Run bounded Logic Coder/Verifier over frozen Reviewer decisions."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_agent_sdk import __version__ as sdk_version

from manim_quality.logic.eval_manifest import load_frozen_eval_manifest
from manim_quality.revisions.fingerprint import sha256_bytes

from ._logic_repair_case import RepairRunConfig, run_repair_case
from ._logic_repair_metrics import RepairCaseMetrics, summarize_repairs
from ._logic_repair_review_bundle import review_bundle_hash
from ._logic_shadow_io import write_json

_PROVIDER_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


def main() -> int:
    args = _arguments()
    dataset_root = args.dataset_root.resolve(strict=True)
    review_root = args.review_root.resolve(strict=True)
    source_report = review_root / "shadow_report.json"
    actual_sha = sha256_bytes(source_report.read_bytes())
    if actual_sha != _canonical_sha(args.review_report_sha256):
        raise SystemExit("frozen Reviewer report hash mismatch")
    actual_bundle_sha = review_bundle_hash(review_root)
    if actual_bundle_sha != _canonical_sha(args.review_bundle_sha256):
        raise SystemExit("frozen Reviewer bundle hash mismatch")
    manifests = [
        load_frozen_eval_manifest(path, dataset_root=dataset_root)
        for path in args.manifest
    ]
    cases = [case for manifest in manifests for case in manifest.cases]
    cases = _select_cases(cases, args.sample_id, args.limit)
    config = RepairRunConfig(
        args.model,
        _provider_environment(os.environ),
        review_root,
        args.output.resolve(),
    )
    results = _run_cases(cases, dataset_root, config, args.workers)
    upstream = json.loads(source_report.read_text(encoding="utf-8"))
    metrics = summarize_repairs(tuple(results))
    payload = {
        "schema_version": "manim-quality.logic-repair-shadow.v1",
        "model": args.model,
        "claude_agent_sdk_version": sdk_version,
        "packs": [manifest.pack_id for manifest in manifests],
        "source_reviewer_report_sha256": actual_sha,
        "source_reviewer_bundle_sha256": actual_bundle_sha,
        "source_reviewer_metrics": _summary_metrics(upstream),
        "render_validation": "not_run_task9",
        "metrics": metrics,
    }
    write_json(config.output_root / "repair_shadow_report.json", payload)
    _print_summary(metrics)
    return 0


def _run_cases(cases, root, config, workers) -> list[RepairCaseMetrics]:
    by_id: dict[str, RepairCaseMetrics] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                run_repair_case, case, dataset_root=root, config=config
            ): case
            for case in cases
        }
        for future in as_completed(futures):
            case = futures[future]
            result = future.result()
            by_id[case.sample_id] = result
            print(
                f"[{len(by_id)}/{len(cases)}] {case.sample_id}: {result.status}",
                flush=True,
            )
    return [by_id[case.sample_id] for case in cases]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        default=None,
    )
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--review-report-sha256", required=True)
    parser.add_argument("--review-bundle-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-id", action="append")
    args = parser.parse_args()
    if args.manifest is None:
        args.manifest = [
            root / "logic_known_bad" / "manifest.json",
            root / "logic_known_bad_replacement" / "manifest.json",
            root / "logic_known_good" / "manifest.json",
        ]
    if not 1 <= args.workers <= 4:
        parser.error("--workers must be between 1 and 4")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def _select_cases(cases, requested, limit):
    if requested:
        wanted = set(requested)
        cases = [case for case in cases if case.sample_id in wanted]
        missing = wanted - {case.sample_id for case in cases}
        if missing:
            raise SystemExit(f"unknown sample id(s): {', '.join(sorted(missing))}")
    if limit is not None:
        cases = cases[:limit]
    if not cases:
        raise SystemExit("no repair cases selected")
    return cases


def _provider_environment(environ: Mapping[str, str]) -> dict[str, str]:
    values = {
        name: value
        for name in _PROVIDER_ENV
        if (value := environ.get(name, "")).strip()
    }
    if not any(name in values for name in _PROVIDER_ENV[1:]):
        raise SystemExit("provider authentication is required")
    return values


def _canonical_sha(value: str) -> str:
    text = value.strip().lower().removeprefix("sha256:")
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise SystemExit("--review-report-sha256 must be a SHA-256 digest")
    return f"sha256:{text}"


def _summary_metrics(payload: object) -> object:
    if not isinstance(payload, dict) or not isinstance(payload.get("metrics"), dict):
        raise SystemExit("frozen Reviewer report has invalid metrics")
    return {key: value for key, value in payload["metrics"].items() if key != "cases"}


def _print_summary(metrics: dict[str, object]) -> None:
    print(
        "repair summary: "
        f"attempted={metrics['repair_attempted']} "
        f"ready={metrics['candidate_ready']} "
        f"target_restored={metrics['target_restored']} "
        f"over_edit={metrics['known_good_over_edit']} "
        f"errors={metrics['errors']} "
        f"tokens={metrics['total_tokens']}",
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
