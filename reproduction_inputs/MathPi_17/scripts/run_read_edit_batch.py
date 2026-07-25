from __future__ import annotations

import argparse
import asyncio
import ast
import difflib
import json
import os
import py_compile
import shutil
import time
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolUseBlock,
    query,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CASES_ROOT = PACKAGE_ROOT / "cases"
RUNS_ROOT = PACKAGE_ROOT / "runs"


def case_dirs() -> list[Path]:
    values = sorted(path for path in CASES_ROOT.iterdir() if path.is_dir())
    if len(values) != 17:
        raise ValueError(f"expected 17 cases, found {len(values)}")
    return values


def prepare(case: Path, run_root: Path) -> tuple[Path, dict[str, object]]:
    workspace = run_root / case.name
    workspace.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(case / "source" / "main.py", workspace / "candidate.py")
    shutil.copyfile(case / "source" / "record.json", workspace / "record.json")
    shutil.copytree(case / "assets", workspace / "assets")
    record = json.loads((workspace / "record.json").read_text(encoding="utf-8"))
    return workspace, record


def repair_prompt(record: dict[str, object]) -> str:
    problem = str(record.get("problem_text") or record.get("title") or "")
    return f"""You are the single Logic Repair Agent for one Manim candidate.
Do not delegate work. Do not call Agent or Task. Use Read to inspect the
allowlisted candidate.py, diagnose all dynamic-geometry logic defects, then use
Edit to apply the smallest coordinated repair directly in candidate.py.

Audit every independent diagram and every phase:
1. Trace anchors through fit/scale/move and refresh stale coordinate arrays.
2. Check Mobjects created after transforms and every ValueTracker/updater.
3. Check every Mobject passed to Create/Write/FadeIn/Indicate/Transform or a
   custom highlight function. It must belong to its phase owner VGroup or be
   explicitly removed when the phase ends.
4. Check inline Line/Polygon/MathTex objects and objects created after an owner
   VGroup was assembled; prevent transient_mobject_lifecycle_leak.
5. Verify the mathematical construction against the problem statement.

Do not hide drift with magic shifts. Do not rewrite narration, styling, colors,
headers, helpers, imports, BaseConfigScene, or code outside class Solution.
After editing, Read the changed region once and return a concise summary.

PROBLEM:
{problem}
"""


def options(workspace: Path, model: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model=model,
        tools=["Read", "Edit"],
        allowed_tools=["Read", "Edit"],
        disallowed_tools=[
            "Agent",
            "Task",
            "Bash",
            "Write",
            "Glob",
            "Grep",
            "NotebookEdit",
            "Skill",
            "WebFetch",
            "WebSearch",
        ],
        permission_mode="acceptEdits",
        cwd=str(workspace),
        max_turns=24,
        setting_sources=[],
        env={
            "ANTHROPIC_BASE_URL": required_env("ANTHROPIC_BASE_URL"),
            "ANTHROPIC_API_KEY": required_env("ANTHROPIC_API_KEY"),
        },
    )


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


def only_solution_changed(before: str, after: str) -> bool:
    def outside(source: str) -> tuple[str, str]:
        tree = ast.parse(source)
        node = next(
            item
            for item in tree.body
            if isinstance(item, ast.ClassDef) and item.name == "Solution"
        )
        lines = source.splitlines(keepends=True)
        return "".join(lines[: node.lineno - 1]), "".join(lines[node.end_lineno :])

    return outside(before) == outside(after)


async def run_case(
    source_case: Path,
    run_root: Path,
    semaphore: asyncio.Semaphore,
    model: str,
) -> dict[str, object]:
    async with semaphore:
        workspace, record = prepare(source_case, run_root)
        candidate = workspace / "candidate.py"
        before = candidate.read_text(encoding="utf-8")
        started = time.monotonic()
        tools: list[dict[str, object]] = []
        result: ResultMessage | None = None
        error: str | None = None
        final_text = ""
        scope_ok = False
        try:
            async for message in query(
                prompt=repair_prompt(record),
                options=options(workspace, model),
            ):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, ToolUseBlock):
                            tools.append({"name": block.name, "input": block.input})
                elif isinstance(message, ResultMessage):
                    result = message
                    final_text = str(message.result or "")
            if result is None:
                raise RuntimeError("missing ResultMessage")
            if result.is_error:
                raise RuntimeError(str(result.errors or result.subtype))
            after = candidate.read_text(encoding="utf-8")
            ast.parse(after)
            py_compile.compile(str(candidate), doraise=True)
            scope_ok = only_solution_changed(before, after)
            if not scope_ok:
                raise RuntimeError("change escaped class Solution")
            (workspace / "changes.diff").write_text(
                "".join(
                    difflib.unified_diff(
                        before.splitlines(keepends=True),
                        after.splitlines(keepends=True),
                        fromfile="source/main.py",
                        tofile="candidate.py",
                    )
                ),
                encoding="utf-8",
            )
        except Exception as caught:
            error = f"{type(caught).__name__}: {caught}"
            after = candidate.read_text(encoding="utf-8")
            try:
                scope_ok = only_solution_changed(before, after)
            except (SyntaxError, StopIteration):
                scope_ok = False
        payload = {
            "case": source_case.name,
            "model": model,
            "status": "success" if error is None else "error",
            "changed": after != before,
            "only_solution_changed": scope_ok,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "turns": getattr(result, "num_turns", None),
            "usage": getattr(result, "usage", None),
            "total_cost_usd": getattr(result, "total_cost_usd", None),
            "tool_calls": tools,
            "final_text": final_text,
            "error": error,
        }
        (workspace / "result.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "case": source_case.name,
                    "status": payload["status"],
                    "read": sum(item["name"] == "Read" for item in tools),
                    "edit": sum(item["name"] == "Edit" for item in tools),
                    "seconds": payload["elapsed_seconds"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return payload


async def run_all(workers: int, model: str, run_id: str) -> int:
    run_root = RUNS_ROOT / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    semaphore = asyncio.Semaphore(workers)
    results = await asyncio.gather(
        *(run_case(case, run_root, semaphore, model) for case in case_dirs())
    )
    summary = {
        "run_id": run_id,
        "model": model,
        "workers": workers,
        "attempted": len(results),
        "success": sum(item["status"] == "success" for item in results),
        "errors": sum(item["status"] == "error" for item in results),
        "read_calls": sum(
            tool["name"] == "Read"
            for item in results
            for tool in item["tool_calls"]
        ),
        "edit_calls": sum(
            tool["name"] == "Edit"
            for item in results
            for tool in item["tool_calls"]
        ),
        "cases": results,
    }
    (run_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return 0 if summary["errors"] == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=int(os.getenv("REPAIR_WORKERS", "8")))
    parser.add_argument("--model", default=os.getenv("QUALITY_MODEL", "gpt-5.6-sol"))
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    args = parser.parse_args()
    if not 1 <= args.workers <= 17:
        parser.error("--workers must be between 1 and 17")
    return asyncio.run(run_all(args.workers, args.model, args.run_id))


if __name__ == "__main__":
    raise SystemExit(main())
