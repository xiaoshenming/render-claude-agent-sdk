"""Run the expected-versus-actual relation probe on paired source code."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from claude_agent_sdk import __version__ as sdk_version

from manim_quality.agents import (
    AgentRuntime,
    BudgetLimits,
    ClaudeSdkBackend,
    reviewer_profile,
)
from manim_quality.contracts._json_values import thaw_json_object
from manim_quality.logic.expectations.extractor import ExpectedRelationExtractor

from ._expected_relation_probe import evaluate_code, resolve_scene_id
from ._expected_relation_probe_io import (
    build_report,
    case_dir,
    error_text,
    integer,
    json_object,
    print_metrics,
    provider_environment,
    required,
    selection,
)
from ._logic_shadow_io import JsonUsageSink, write_json


def main() -> int:
    args = _arguments()
    dataset = args.dataset_root.resolve(strict=True)
    selected = selection(args.selection)
    output = args.output.resolve()
    cases = [case_dir(dataset, sample_id) for sample_id in selected]
    results = _run_cases(cases, output, args.model, args.workers)
    report = build_report(results, args.model, sdk_version)
    write_json(output / "probe_report.json", report)
    print_metrics(report["metrics"])
    return 0


def _run_cases(
    cases: Sequence[Path], output: Path, model: str, workers: int
) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_run_case, case, output, model): case.name for case in cases
        }
        for future in as_completed(futures):
            sample_id = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {"sample_id": sample_id, "error": error_text(error)}
            by_id[sample_id] = result
            state = "error" if result.get("error") else "done"
            print(f"[{len(by_id)}/{len(cases)}] {sample_id}: {state}", flush=True)
    return [by_id[case.name] for case in cases]


def _run_case(case: Path, output: Path, model: str) -> dict[str, object]:
    sample_id = case.name
    case_output = output / "cases" / sample_id
    sink = JsonUsageSink(case_output / "agent_call.json")
    problem_source = required(case, "problem_text.txt")
    with tempfile.TemporaryDirectory(
        prefix="expected-relation-", ignore_cleanup_errors=True
    ) as temporary:
        workspace = Path(temporary)
        problem = workspace / "problem_text.txt"
        shutil.copyfile(problem_source, problem)
        runtime = AgentRuntime(
            ClaudeSdkBackend(provider_env=provider_environment(os.environ)),
            sink,
            _limits(),
        )
        extractor = ExpectedRelationExtractor(
            runtime=runtime,
            profile=reviewer_profile(
                model=model,
                prompt_version="expected-relations-v1",
                schema_version="expected-relations-v1",
                tool_version=f"claude-agent-sdk-{sdk_version}-read-v1",
            ),
        )
        estimate = max(1_000, problem.stat().st_size // 2)
        extraction = extractor.extract(
            run_id=f"expected-{sample_id}",
            workspace=workspace,
            source_path=problem,
            estimated_input_tokens=estimate,
            reserved_output_tokens=20_000,
        )
    contract = extraction.contract
    meta = json_object(required(case, "sample_meta.json"))
    truth = json_object(required(case, "mutation_ground_truth.json"))
    mutated_code = required(case, "candidate.py").read_text(encoding="utf-8-sig")
    original_code = required(case, "original_candidate.py").read_text(
        encoding="utf-8-sig"
    )
    scene_id = resolve_scene_id(meta, mutated_code)
    target_line = integer(truth, "line_no")
    mutated = evaluate_code(
        mutated_code,
        scene_id,
        contract,
        target_line=target_line,
    )
    original = evaluate_code(
        original_code,
        scene_id,
        contract,
    )
    contract_payload = thaw_json_object(extraction.call_record.structured_output or {})
    write_json(case_output / "expected_relations.json", contract_payload)
    write_json(case_output / "mutated_comparison.json", mutated.to_dict())
    write_json(case_output / "original_comparison.json", original.to_dict())
    record = extraction.call_record
    return {
        "sample_id": sample_id,
        "source_sample_id": meta.get("source_sample_id"),
        "mutation_type": truth.get("mutation_type"),
        "scene_id": scene_id,
        "claim_count": len(contract.claims),
        "mutated": mutated.to_dict(),
        "original": original.to_dict(),
        "usage": {
            "input_tokens": record.usage.input_tokens,
            "output_tokens": record.usage.output_tokens,
            "cache_read_tokens": record.usage.cache_read_tokens,
            "cache_write_tokens": record.usage.cache_write_tokens,
            "total_tokens": record.usage.total_tokens,
            "turns": record.turns,
            "model_rounds": record.observed_model_rounds,
            "elapsed_ms": record.elapsed_ms,
        },
        "error": None,
    }


def _limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=50_000,
        max_turns=3,
        max_tool_calls=4,
        max_elapsed_ms=180_000,
        max_input_tokens=30_000,
        max_output_tokens=35_000,
        max_cache_read_tokens=30_000,
        max_cache_write_tokens=30_000,
        max_total_tokens=100_000,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path(__file__).parent / "expected_relation_probe_v1" / "selection.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.workers <= 6:
        parser.error("--workers must be between 1 and 6")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
