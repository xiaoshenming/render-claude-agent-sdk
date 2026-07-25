"""Run the read-only Logic Reviewer over all frozen good/bad shadow cases."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_agent_sdk import __version__ as sdk_version

from manim_quality.logic.eval_manifest import load_frozen_eval_manifest
from manim_quality.logic.review_input import ReviewInputVersion
from manim_quality.logic.shadow import ShadowCaseResult, summarize_shadow

from ._logic_shadow_case import ShadowRunConfig, run_shadow_case

_PROVIDER_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


def main() -> int:
    args = _arguments()
    dataset_root = _dataset_root(args.dataset_root)
    manifests = [
        load_frozen_eval_manifest(path, dataset_root=dataset_root)
        for path in args.manifest
    ]
    if args.verify_only:
        count = sum(len(manifest.cases) for manifest in manifests)
        print(f"verified {len(manifests)} frozen packs and {count} cases")
        return 0
    model = args.model or os.environ.get("MANIM_QUALITY_REVIEW_MODEL")
    if not model:
        raise SystemExit("--model or MANIM_QUALITY_REVIEW_MODEL is required")
    if args.output is None:
        raise SystemExit("--output is required unless --verify-only is used")
    cases = [case for manifest in manifests for case in manifest.cases]
    if args.sample_id:
        requested = set(args.sample_id)
        cases = [case for case in cases if case.sample_id in requested]
        missing = requested - {case.sample_id for case in cases}
        if missing:
            raise SystemExit(f"unknown sample id(s): {', '.join(sorted(missing))}")
    if args.limit is not None:
        cases = cases[: args.limit]
    if not cases:
        raise SystemExit("no evaluation cases selected")
    output = args.output.resolve()
    config = ShadowRunConfig(
        model=model,
        provider_env=_provider_environment(os.environ),
        output_root=output,
        input_version=ReviewInputVersion(args.input_version),
    )
    results = _run_cases(cases, dataset_root, config, args.workers)
    report = summarize_shadow(tuple(results))
    payload = {
        "schema_version": "manim-quality.logic-shadow-report.v1",
        "model": model,
        "claude_agent_sdk_version": sdk_version,
        "review_input_version": config.input_version.value,
        "packs": [manifest.pack_id for manifest in manifests],
        "requested_case_count": len(cases),
        "metrics": report.to_dict(),
    }
    _write_json(output / "shadow_report.json", payload)
    _print_summary(payload["metrics"])
    return 0


def _run_cases(cases, root: Path, config: ShadowRunConfig, workers: int):
    by_id: dict[str, ShadowCaseResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                run_shadow_case, case, dataset_root=root, config=config
            ): case
            for case in cases
        }
        for future in as_completed(futures):
            case = futures[future]
            result = future.result()
            by_id[case.sample_id] = result
            state = result.decision.value if result.decision else "error"
            print(f"[{len(by_id)}/{len(cases)}] {case.sample_id}: {state}", flush=True)
    return [by_id[case.sample_id] for case in cases]


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent
    parser.add_argument(
        "--manifest",
        type=Path,
        action="append",
        default=[
            root / "logic_known_bad" / "manifest.json",
            root / "logic_known_bad_replacement" / "manifest.json",
            root / "logic_known_good" / "manifest.json",
        ],
    )
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument("--model")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-id", action="append")
    parser.add_argument(
        "--input-version",
        choices=[item.value for item in ReviewInputVersion],
        default=ReviewInputVersion.EVIDENCE_V1.value,
    )
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 8:
        parser.error("--workers must be between 1 and 8")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    return args


def _dataset_root(value: Path | None) -> Path:
    if value is None:
        raw = os.environ.get("MANIM_LOGIC_EVAL_PACKS_ROOT")
        if not raw:
            raise SystemExit(
                "--dataset-root or MANIM_LOGIC_EVAL_PACKS_ROOT is required"
            )
        value = Path(raw)
    return value.resolve(strict=True)


def _provider_environment(environ: Mapping[str, str]) -> dict[str, str]:
    values = {
        name: value
        for name in _PROVIDER_ENV
        if (value := environ.get(name, "")).strip()
    }
    if not any(
        name in values for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")
    ):
        raise SystemExit("provider authentication is required")
    return values


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _print_summary(metrics: object) -> None:
    data = metrics if isinstance(metrics, dict) else {}
    print(
        "shadow summary: "
        f"attempted={data.get('attempted')} "
        f"recall={data.get('detection_recall')} "
        f"false_positive_rate={data.get('false_positive_rate')} "
        f"errors={data.get('errors')} "
        f"tokens={data.get('total_tokens')}",
        flush=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
