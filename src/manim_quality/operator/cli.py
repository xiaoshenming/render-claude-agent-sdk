"""CLI entrypoint for the unified Quality Operator."""

from __future__ import annotations

import argparse
import json
import os
import signal
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.profile import operator_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage_ledger import RecordingJsonlUsageLedger

from .agent import QualityOperatorAgent
from .defaults import PARENT_MAX_TOOL_CALLS, PARENT_MAX_TURNS
from .harness import QualityHarness
from .problem_source import extract_problem_text
from .runtime_tools import (
    RealLayoutInspector,
    RealRevisionValidator,
    RuntimeToolchain,
    geometry_sidecar_runner,
)
from .services import (
    BasicRelationChecker,
    CompileOnlyValidator,
    UnverifiedLayoutInspector,
)
from .source_view import extract_solution


def _install_sigterm_handler() -> None:
    """Convert batch-level SIGTERM into an exception the harness can
    catch, so failure evidence is persisted before the process exits.
    Detached render sessions are reaped first: a supervisor's group kill
    cannot reach them, and orphaned containers would hold render slots."""

    def _raise(signum, frame):
        del signum, frame
        from .runtime_tools.process import kill_active_process_groups

        kill_active_process_groups()
        raise TimeoutError("case timeout: SIGTERM received from batch runner")

    try:
        signal.signal(signal.SIGTERM, _raise)
    except ValueError:
        pass  # not the main thread; embedding caller owns signal handling


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    _install_sigterm_handler()
    candidate = args.candidate.resolve(strict=True).read_text(encoding="utf-8")
    problem = _problem_identity(candidate, args.problem)
    solution_steps = _text_input(args.solution_steps)
    repair_feedback = _json_input(args.repair_feedback)
    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise SystemExit("--workspace must be a directory")
    sink = RecordingJsonlUsageLedger(args.output / "logs/usage-events.jsonl")
    backend = ClaudeSdkBackend(
        provider_env=_provider_environment(
            os.environ,
            allow_ambient=args.allow_ambient_login,
        )
    )
    runtime = AgentRuntime(backend, sink, _limits(args))
    operator = QualityOperatorAgent(
        runtime=runtime,
        profile=operator_profile(
            model=args.model,
            prompt_version="quality-operator-v3",
            schema_version="quality-operator-output-v1",
            tool_version="quality-tools-v1",
        ),
    )
    harness = _harness(operator, args, workspace)
    result = harness.run(
        run_id=args.run_id or f"quality-{uuid.uuid4().hex}",
        workspace=workspace,
        artifact_root=args.output,
        problem_text=problem,
        solution_steps=solution_steps,
        repair_feedback=repair_feedback,
        candidate_code=candidate,
        estimated_input_tokens=args.estimated_input_tokens,
        reserved_output_tokens=args.reserved_output_tokens,
    )
    record = result.operator_result.call_record
    print(
        json.dumps(
            {
                "decision": result.gate_result.decision.value,
                "reasons": list(result.gate_result.reasons),
                "submitted_revision_id": result.operator_result.revision.revision_id,
                "turns": record.turns,
                "tool_calls": len(record.tool_calls),
                "tokens": record.usage.total_tokens,
                "artifacts": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if result.gate_result.decision.value == "PROPOSED" else 2


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the unified Quality Agent with real Manim render and layout "
            "verification. Use --compile-only only for SDK smoke diagnosis."
        )
    )
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--problem", type=Path)
    parser.add_argument("--solution-steps", type=Path)
    parser.add_argument("--repair-feedback", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument(
        "--manim-python",
        type=Path,
        help="Python executable containing Manim and task runtime dependencies.",
    )
    parser.add_argument(
        "--runtime-python-path",
        type=Path,
        action="append",
        default=[],
        help="Import root required by generated code; repeat when needed.",
    )
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--allow-ambient-login", action="store_true")
    parser.add_argument("--render-cache", action="store_true")
    parser.add_argument("--render-cache-dir", type=Path)
    parser.add_argument("--max-turns", type=int, default=PARENT_MAX_TURNS)
    parser.add_argument(
        "--max-tool-calls",
        type=int,
        default=PARENT_MAX_TOOL_CALLS,
    )
    parser.add_argument("--estimated-input-tokens", type=int, default=4_000)
    parser.add_argument("--reserved-output-tokens", type=int, default=2_000)
    args = parser.parse_args(argv)
    for name in (
        "max_turns",
        "max_tool_calls",
        "estimated_input_tokens",
        "reserved_output_tokens",
    ):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    return args


def _harness(operator, args, workspace: Path) -> QualityHarness:
    if args.compile_only:
        return QualityHarness(
            operator=operator,
            relation_checker=BasicRelationChecker(),
            agent_layout_inspector=UnverifiedLayoutInspector(),
            agent_revision_validator=CompileOnlyValidator(),
            acceptance_layout_inspector=UnverifiedLayoutInspector(),
            acceptance_revision_validator=CompileOnlyValidator(),
        )
    if args.manim_python is None:
        raise SystemExit("--manim-python is required outside --compile-only mode")
    manim_python = args.manim_python.resolve(strict=True)
    if not manim_python.is_file():
        raise SystemExit("--manim-python must be a file")
    environment = _worker_environment(args)
    # The frozen probe runner is executed via the sidecar tee wrapper so the
    # versioned layout policy receives real stroke geometry. The wrapper never
    # alters the frozen runner's classification or stdout contract.
    environment["MANIM_LAYOUT_PROBE_DELEGATE"] = str(
        Path(__file__).resolve().parents[3]
        / "vendor"
        / "layout_probe"
        / "probe_runner.txt"
    )
    runner = Path(geometry_sidecar_runner.__file__).resolve()
    shared_render_cache = (
        args.render_cache_dir.resolve()
        if args.render_cache_dir is not None
        else args.output / "render_cache"
        if args.render_cache else None
    )
    if shared_render_cache is not None:
        shared_render_cache.mkdir(parents=True, exist_ok=True)
    agent_chain = RuntimeToolchain(
        source_workspace=workspace,
        artifact_root=args.output / "agent_runtime",
        probe_runner=runner,
        python_executable=manim_python,
        environment=environment,
        render_cache_dir=shared_render_cache,
    )
    layout = RealLayoutInspector(agent_chain)
    validator = RealRevisionValidator(agent_chain)
    return QualityHarness(
        operator=operator,
        relation_checker=BasicRelationChecker(),
        agent_layout_inspector=layout,
        agent_revision_validator=validator,
        acceptance_layout_inspector=layout,
        acceptance_revision_validator=validator,
    )


def _worker_environment(args) -> dict[str, str]:
    environment: dict[str, str] = {}
    roots = [path.resolve(strict=True) for path in args.runtime_python_path]
    if roots:
        environment["PYTHONPATH"] = os.pathsep.join(str(path) for path in roots)
    if args.assets_dir is not None:
        assets = args.assets_dir.resolve(strict=True)
        if not assets.is_dir():
            raise SystemExit("--assets-dir must be a directory")
        environment["MATHPI_RENDER_ASSETS_DIR"] = str(assets)
    return environment


def _provider_environment(
    environ: Mapping[str, str],
    *,
    allow_ambient: bool = False,
) -> dict[str, str]:
    values: dict[str, str] = {}
    base_url = environ.get("ANTHROPIC_BASE_URL", "").strip()
    if base_url:
        values["ANTHROPIC_BASE_URL"] = base_url
    api_key = environ.get("ANTHROPIC_API_KEY", "").strip()
    auth_token = environ.get("ANTHROPIC_AUTH_TOKEN", "").strip()
    if api_key:
        values["ANTHROPIC_API_KEY"] = api_key
        values["ANTHROPIC_AUTH_TOKEN"] = ""
    elif auth_token:
        values["ANTHROPIC_AUTH_TOKEN"] = auth_token
    elif not allow_ambient or base_url:
        # A custom gateway without a credential is a misconfiguration, and
        # falling back to the machine's official login session must be an
        # explicit operator decision, never a silent default.
        raise SystemExit(
            "provider authentication is required "
            "(pass --allow-ambient-login to use the official login session)"
        )
    # Empty mapping: the SDK CLI resolves the official login session.
    return values


def _problem_identity(candidate: str, problem_path: Path | None) -> str:
    if problem_path is not None:
        return problem_path.resolve(strict=True).read_text(encoding="utf-8")
    try:
        return extract_problem_text(candidate)
    except ValueError:
        return f"solution-source:{extract_solution(candidate).sha256}"


def _text_input(path: Path | None) -> str:
    return path.resolve(strict=True).read_text(encoding="utf-8") if path else ""


def _json_input(path: Path | None) -> dict[str, object]:
    if path is None:
        return {}
    value = json.loads(path.resolve(strict=True).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("--repair-feedback must contain one JSON object")
    return value


def _limits(args: argparse.Namespace) -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=2_000_000,
        max_turns=args.max_turns,
        max_tool_calls=args.max_tool_calls,
        max_elapsed_ms=3_600_000,
        max_input_tokens=600_000,
        max_output_tokens=80_000,
        max_cache_read_tokens=2_000_000,
        max_cache_write_tokens=600_000,
        max_total_tokens=2_500_000,
    )
