from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent_repair import run_case_agent
from .contracts import prepare_sample
from .enterprise_guards import validate_sample_pack_manifest
from .freeze_manifest import freeze_source_root, verify_freeze_manifest
from .holdout_audit import write_holdout_audit
from .mutation_eval import generate_mutation_pack
from .render_check import run_render_check
from .review_input import write_review_input
from .round_report import write_round_reports
from .round_runner import run_round, write_run_round_result
from .run_manager import advance_case_from_review, init_baseline_run, run_case_reviewer
from .settings import load_agent_config, load_reviewer_config
from .validator import validate_contract


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "prepare":
        result = prepare_sample(args.sample, args.out)
        _emit_json(
            {
                "ok": True,
                "sample_id": result.sample_id,
                "workdir": str(result.workdir),
                "contract": str(result.contract_path),
                "source_region": str(result.source_region_path),
            }
        )
        return 0

    if args.command == "prepare-batch":
        prepared = []
        for sample_dir in sorted(p for p in args.samples_root.iterdir() if p.is_dir()):
            if not (sample_dir / "candidate.py").exists() or not (sample_dir / "issue.json").exists():
                continue
            result = prepare_sample(sample_dir, args.out)
            prepared.append({"sample_id": result.sample_id, "workdir": str(result.workdir)})
        _emit_json({"ok": True, "prepared_count": len(prepared), "prepared": prepared})
        return 0

    if args.command == "check":
        payload = validate_contract(args.code, args.contract)
        _emit_json(payload)
        return 0 if payload["passed"] else 1

    if args.command == "review-input":
        out_path = write_review_input(args.sample, args.out)
        _emit_json({"ok": True, "out": str(out_path)})
        return 0

    if args.command == "validate-pack":
        payload = validate_sample_pack_manifest(args.manifest)
        _emit_json(payload)
        return 0 if payload["ok"] else 1

    if args.command == "mutate-pack":
        difficulties = tuple(args.difficulty) if args.difficulty else ("medium", "hard", "expert")
        payload = generate_mutation_pack(
            args.samples_root,
            args.out,
            limit=args.limit,
            seed=args.seed,
            allowed_difficulties=difficulties,
            variants_per_source=args.variants_per_source,
        )
        _emit_json(payload)
        return 0

    if args.command == "init-baseline":
        payload = init_baseline_run(args.samples_root, args.out, limit=args.limit)
        _emit_json(payload)
        return 0

    if args.command == "review-case":
        payload = run_case_reviewer(args.case_dir, load_reviewer_config())
        _emit_json(payload)
        return 0

    if args.command == "agent-case":
        payload = run_case_agent(
            args.case_dir,
            load_agent_config(),
            max_turns=args.max_turns,
            max_budget_usd=args.max_budget_usd,
            repair_mode=args.repair_mode,
        )
        _emit_json(payload)
        return 0

    if args.command == "advance-case":
        payload = advance_case_from_review(
            args.case_dir,
            allow_soft_repair=args.allow_soft_repair,
            allow_open_repair=args.allow_open_repair,
        )
        _emit_json(payload)
        return 0

    if args.command == "report-round":
        payload = write_round_reports(args.round_dir)
        _emit_json(payload)
        return 0

    if args.command == "render-case":
        payload = run_render_check(
            args.case_dir,
            command=args.render_command or None,
            scene_names=args.scene,
            affected_only=args.affected_only,
            quality=args.quality,
            timeout_sec=args.timeout_sec,
        )
        _emit_json(payload)
        return 0 if payload["passed"] else 1

    if args.command == "audit-holdout":
        payload = write_holdout_audit(args.manifest, args.runs_root, args.out, min_count=args.min_count)
        _emit_json(payload)
        return 0 if payload["ok"] else 1

    if args.command == "run-round":
        payload = run_round(
            args.round_dir,
            dry_run=args.dry_run,
            render=not args.no_render,
            max_turns=args.max_turns,
            max_budget_usd=args.max_budget_usd,
            render_timeout_sec=args.render_timeout_sec,
            repair_mode=args.repair_mode,
            allow_soft_repair=args.allow_soft_repair,
            allow_open_repair=args.allow_open_repair,
        )
        if args.out:
            write_run_round_result(args.out, payload)
        _emit_json(payload)
        return 0 if payload["ok"] else 1

    if args.command == "freeze-code":
        if args.verify:
            payload = verify_freeze_manifest(args.verify, root=args.source_root)
        else:
            payload = freeze_source_root(args.source_root, args.out, label=args.label)
        _emit_json(payload)
        return 0 if payload["ok"] else 1

    raise AssertionError(f"unhandled command: {args.command}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare and validate logic repair MVP contracts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Prepare one sample workdir.")
    prepare.add_argument("--sample", required=True, type=Path, help="Sample dir containing candidate.py and issue.json.")
    prepare.add_argument("--out", required=True, type=Path, help="Output root for prepared workdir.")

    prepare_batch = subparsers.add_parser("prepare-batch", help="Prepare every valid sample dir under a root.")
    prepare_batch.add_argument("--samples-root", required=True, type=Path, help="Root containing sample subdirectories.")
    prepare_batch.add_argument("--out", required=True, type=Path, help="Output root for prepared workdirs.")

    check = subparsers.add_parser("check", help="Validate code against a logic contract.")
    check.add_argument("--code", required=True, type=Path, help="Path to candidate.py or fixed candidate.")
    check.add_argument("--contract", required=True, type=Path, help="Path to logic_contract_context.json.")

    review_input = subparsers.add_parser("review-input", help="Build a clean input packet for an LLM logic reviewer.")
    review_input.add_argument("--sample", required=True, type=Path, help="Sample dir containing candidate.py.")
    review_input.add_argument("--out", required=True, type=Path, help="Output JSON path.")

    validate_pack = subparsers.add_parser("validate-pack", help="Validate enterprise sample-pack constraints.")
    validate_pack.add_argument("--manifest", required=True, type=Path, help="Path to sample pack manifest.csv.")

    mutate_pack = subparsers.add_parser("mutate-pack", help="Generate a logic mutation eval sample pack.")
    mutate_pack.add_argument("--samples-root", required=True, type=Path, help="Root containing source sample dirs.")
    mutate_pack.add_argument("--out", required=True, type=Path, help="Output root for mutation sample pack.")
    mutate_pack.add_argument("--limit", type=int, help="Maximum mutated samples to create.")
    mutate_pack.add_argument("--seed", type=int, default=0, help="Deterministic mutation seed.")
    mutate_pack.add_argument(
        "--variants-per-source",
        type=int,
        default=1,
        help="Maximum mutation variants to create from each source sample.",
    )
    mutate_pack.add_argument(
        "--difficulty",
        action="append",
        choices=("medium", "hard", "expert"),
        default=[],
        help="Allowed mutation difficulty. Can be repeated. Defaults to all supported difficulties.",
    )

    init_baseline = subparsers.add_parser("init-baseline", help="Initialize a traceable round_0_baseline run dir.")
    init_baseline.add_argument("--samples-root", required=True, type=Path, help="Path to normalized sample dirs.")
    init_baseline.add_argument("--out", required=True, type=Path, help="Run output root.")
    init_baseline.add_argument("--limit", type=int, help="Optional sample limit for smoke runs.")

    review_case = subparsers.add_parser("review-case", help="Run the configured LLM reviewer for one prepared case dir.")
    review_case.add_argument("--case-dir", required=True, type=Path, help="Prepared run case dir.")

    agent_case = subparsers.add_parser("agent-case", help="Run Claude Agent SDK repair for one prepared case dir.")
    agent_case.add_argument("--case-dir", required=True, type=Path, help="Prepared run case dir.")
    agent_case.add_argument("--max-turns", type=int, default=6, help="SDK max turns for this repair attempt.")
    agent_case.add_argument("--max-budget-usd", type=float, default=0.75, help="SDK budget cap for this repair attempt.")
    agent_case.add_argument(
        "--repair-mode",
        choices=("hybrid", "sdk_only", "direct_patch_only"),
        default="hybrid",
        help="Repair execution mode. Use sdk_only for Agent capability evaluation.",
    )

    advance_case = subparsers.add_parser("advance-case", help="Build verified issues and repair contract from llm_review.json.")
    advance_case.add_argument("--case-dir", required=True, type=Path, help="Prepared run case dir.")
    advance_case.add_argument(
        "--allow-soft-repair",
        action="store_true",
        help="Allow complete but non-deterministically verified LLM issues to become soft Agent repair contracts.",
    )
    advance_case.add_argument(
        "--allow-open-repair",
        action="store_true",
        help="Route suspicious but incomplete reviewer issues into open Agent repair tasks instead of PASS.",
    )

    report_round = subparsers.add_parser("report-round", help="Write summary, CSV, experience, and audit reports for a round dir.")
    report_round.add_argument("--round-dir", required=True, type=Path, help="Round dir containing cases/.")

    render_case = subparsers.add_parser("render-case", help="Run render/check for one prepared case dir.")
    render_case.add_argument("--case-dir", required=True, type=Path, help="Prepared run case dir containing candidate.py.")
    render_case.add_argument("--scene", action="append", help="Optional scene class to render. Can be repeated.")
    render_case.add_argument("--affected-only", action="store_true", help="Render only scenes touched by repair_contract.json source lines.")
    render_case.add_argument("--quality", default="l", help="Manim quality suffix used by the default command.")
    render_case.add_argument("--timeout-sec", type=int, default=300, help="Render command timeout in seconds.")
    render_case.add_argument(
        "--command",
        dest="render_command",
        nargs=argparse.REMAINDER,
        help="Optional command to execute instead of the default Manim command. Must be the final option.",
    )

    audit_holdout = subparsers.add_parser("audit-holdout", help="Check which manifest samples are still valid holdout cases.")
    audit_holdout.add_argument("--manifest", required=True, type=Path, help="Candidate holdout manifest.csv.")
    audit_holdout.add_argument("--runs-root", required=True, type=Path, help="Root containing prior round directories.")
    audit_holdout.add_argument("--out", required=True, type=Path, help="Output JSON audit path.")
    audit_holdout.add_argument("--min-count", type=int, default=1, help="Minimum unseen samples required for success.")

    run_round_parser = subparsers.add_parser("run-round", help="Run or dry-run a prepared round directory.")
    run_round_parser.add_argument("--round-dir", required=True, type=Path, help="Round dir containing cases/.")
    run_round_parser.add_argument("--dry-run", action="store_true", help="Only report planned actions and missing env.")
    run_round_parser.add_argument("--out", type=Path, help="Optional JSON output path.")
    run_round_parser.add_argument("--no-render", action="store_true", help="Skip render-case even after validation passes.")
    run_round_parser.add_argument("--max-turns", type=int, default=6, help="SDK max turns for agent-case.")
    run_round_parser.add_argument("--max-budget-usd", type=float, default=0.75, help="SDK budget cap for agent-case.")
    run_round_parser.add_argument("--render-timeout-sec", type=int, default=420, help="Timeout for affected-scene render smoke.")
    run_round_parser.add_argument(
        "--repair-mode",
        choices=("hybrid", "sdk_only", "direct_patch_only"),
        default="hybrid",
        help="Repair execution mode passed to agent-case.",
    )
    run_round_parser.add_argument(
        "--allow-soft-repair",
        action="store_true",
        help="Allow complete but non-deterministically verified LLM issues to become soft Agent repair contracts.",
    )
    run_round_parser.add_argument(
        "--allow-open-repair",
        action="store_true",
        help="Route suspicious but incomplete reviewer issues into open Agent repair tasks during advance-case.",
    )

    freeze_code = subparsers.add_parser("freeze-code", help="Write or verify a source-code freeze manifest.")
    freeze_code.add_argument("--source-root", required=True, type=Path, help="Source root to hash.")
    freeze_code.add_argument("--out", type=Path, help="Output freeze manifest path.")
    freeze_code.add_argument("--label", default="", help="Optional freeze label.")
    freeze_code.add_argument("--verify", type=Path, help="Existing freeze manifest to verify instead of writing a new one.")

    return parser.parse_args(argv)


def _emit_json(payload: object) -> None:
    text = json.dumps(payload, ensure_ascii=False) + "\n"
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(text)
        sys.stdout.flush()
        return
    buffer.write(text.encode("utf-8", errors="replace"))
    buffer.flush()


if __name__ == "__main__":
    raise SystemExit(main())
