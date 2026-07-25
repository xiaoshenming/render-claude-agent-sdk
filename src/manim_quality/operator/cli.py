"""CLI entrypoint for the unified Quality Operator."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.claude_sdk import ClaudeSdkBackend
from manim_quality.agents.profile import operator_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.agents.usage import AgentCallRecord, UsageSink

from .agent import QualityOperatorAgent
from .harness import QualityHarness
from .problem_source import extract_problem_text
from .runtime_tools import (
    RealLayoutInspector,
    RealRevisionValidator,
    RuntimeToolchain,
)
from .services import (
    BasicRelationChecker,
    CompileOnlyValidator,
    UnverifiedLayoutInspector,
)
from .source_view import extract_solution

_PROVIDER_ENV = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")


class MemoryUsageSink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    candidate = args.candidate.resolve(strict=True).read_text(encoding="utf-8")
    problem = _problem_identity(candidate, args.problem)
    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir():
        raise SystemExit("--workspace must be a directory")
    sink = MemoryUsageSink()
    backend = ClaudeSdkBackend(provider_env=_provider_environment(os.environ))
    runtime = AgentRuntime(backend, sink, _limits(args))
    operator = QualityOperatorAgent(
        runtime=runtime,
        profile=operator_profile(
            model=args.model,
            prompt_version="quality-operator-v1",
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
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--max-tool-calls", type=int, default=14)
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
    runner = (
        Path(__file__).resolve().parents[3]
        / "vendor"
        / "layout_probe"
        / "probe_runner.txt"
    )
    agent_chain = RuntimeToolchain(
        source_workspace=workspace,
        artifact_root=args.output / "agent_runtime",
        probe_runner=runner,
        python_executable=manim_python,
        environment=environment,
    )
    gate_chain = RuntimeToolchain(
        source_workspace=workspace,
        artifact_root=args.output / "acceptance_runtime",
        probe_runner=runner,
        python_executable=manim_python,
        environment=environment,
    )
    return QualityHarness(
        operator=operator,
        relation_checker=BasicRelationChecker(),
        agent_layout_inspector=RealLayoutInspector(agent_chain),
        agent_revision_validator=RealRevisionValidator(agent_chain),
        acceptance_layout_inspector=RealLayoutInspector(gate_chain),
        acceptance_revision_validator=RealRevisionValidator(gate_chain),
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


def _problem_identity(candidate: str, problem_path: Path | None) -> str:
    if problem_path is not None:
        return problem_path.resolve(strict=True).read_text(encoding="utf-8")
    try:
        return extract_problem_text(candidate)
    except ValueError:
        return f"solution-source:{extract_solution(candidate).sha256}"


def _limits(args: argparse.Namespace) -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=2_000_000,
        max_turns=args.max_turns,
        max_tool_calls=args.max_tool_calls,
        max_elapsed_ms=600_000,
        max_input_tokens=200_000,
        max_output_tokens=20_000,
        max_cache_read_tokens=200_000,
        max_cache_write_tokens=200_000,
        max_total_tokens=300_000,
    )
