"""Code-only comparison between the confirmed figure and a candidate Solution."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, replace
from pathlib import Path

from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import AgentRunRequest
from manim_quality.agents.tool_policy import ToolInputPolicy
from manim_quality.contracts._json_values import thaw_json_object

from .source_view import extract_solution

REVIEWER_NAME = "figure_fidelity_reviewer"
PROMPT_PATH = Path(__file__).with_name("prompts") / "figure_fidelity_reviewer_v4.md"
REPAIR_ACTIONS = {"auto_repair", "evidence_only", "human_review"}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["pass", "needs_repair"]},
        "diagnosis": {"type": "string"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string"},
                    "category": {"type": "string", "enum": [
                        "missing_object", "identity_binding", "topology",
                        "line_semantics", "panel_identity", "legal_transform",
                        "orientation_change",
                        "ambiguous_evidence",
                    ]},
                    "repair_action": {
                        "type": "string", "enum": sorted(REPAIR_ACTIONS),
                    },
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_evidence": {"type": "string"},
                    "candidate_evidence": {"type": "string"},
                    "repair_scope": {"type": "string"},
                    "description": {"type": "string"},
                    "authority_status": {"type": "string", "enum": [
                        "supported", "contradicted", "not_stated", "unclear",
                    ]},
                    "source_role": {"type": "string", "enum": [
                        "required_input", "source_extra_or_answer", "unclear",
                    ]},
                    "temporal_status": {"type": "string", "enum": [
                        "corresponding_stage_mismatch", "delayed_but_present",
                        "not_applicable",
                    ]},
                    "semantic_equivalence": {"type": "boolean"},
                    "difference_scope": {"type": "string", "enum": [
                        "base_figure", "runtime_problem_panel",
                        "later_subquestion_stage", "later_solution_content",
                        "decorative",
                    ]},
                },
                "required": [
                    "issue_id", "category", "repair_action", "confidence",
                    "source_evidence", "candidate_evidence", "repair_scope",
                    "description", "authority_status", "source_role",
                    "temporal_status", "semantic_equivalence",
                    "difference_scope",
                ],
                "additionalProperties": False,
            },
        },
        "coverage": {"type": "object"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["decision", "diagnosis", "issues", "coverage", "confidence"],
    "additionalProperties": False,
}


def locate_confirmed_figure(candidate_path: Path) -> Path | None:
    candidates = [candidate_path.parent / "assets/visual/figure.py"]
    assets = os.environ.get("MATHPI_RENDER_ASSETS_DIR", "").strip()
    if assets:
        candidates.append(Path(assets) / "visual/figure.py")
    for path in candidates:
        if path.is_file() and path.stat().st_size:
            return path.resolve()
    return None


def run_figure_fidelity_reviewer(
    runtime,
    *,
    candidate_path: Path,
    problem_text: str,
    model: str,
    solution_steps: str = "",
    effort: str = "low",
    figure_path: Path | None = None,
) -> tuple[dict[str, object] | None, object | None]:
    figure = (figure_path.resolve(strict=True) if figure_path is not None
              else locate_confirmed_figure(candidate_path))
    if figure is None:
        return None, None
    request = _request(
        candidate_path.resolve(strict=True), figure, problem_text,
        solution_steps, model, effort,
    )
    outcome = _run_with_required_reads(runtime, request, candidate_path, figure)
    return _result(outcome), outcome.record


def _request(candidate, figure, problem, steps, model, effort):
    solution = extract_solution(candidate.read_text(encoding="utf-8"))
    solution_count = solution.end_line - solution.start_line + 1
    figure_count = _line_count(figure)
    workspace = Path(os.path.commonpath((candidate, figure))).resolve()
    if workspace.is_file():
        workspace = workspace.parent
    exact_reads = {
        candidate: (solution.start_line, solution_count),
        figure: (1, figure_count),
    }
    prompt = (
        PROMPT_PATH.read_text(encoding="utf-8")
        .replace("{{CANDIDATE_PATH}}", str(candidate))
        .replace("{{SOLUTION_START_LINE}}", str(solution.start_line))
        .replace("{{SOLUTION_LINE_COUNT}}", str(solution_count))
        .replace("{{FIGURE_PATH}}", str(figure))
        .replace("{{FIGURE_LINE_COUNT}}", str(figure_count))
        .replace("{{FIGURE_PLAN}}", _figure_plan(figure))
        .replace("{{PROBLEM_TEXT}}", problem.strip())
        .replace("{{SOLUTION_STEPS}}", steps.strip())
        .strip()
    )
    policy = ToolInputPolicy(
        max_calls=2,
        required_fields=("file_path", "offset", "limit"),
        input_normalizer=_read_normalizer(workspace, exact_reads),
    )
    return AgentRunRequest(
        run_id=f"{REVIEWER_NAME}-{candidate.parent.name}",
        profile=reviewer_profile(
            model=model,
            prompt_version="figure-fidelity-native-read-v4.4",
            schema_version="figure-fidelity-output-v4",
        ),
        prompt=prompt,
        output_schema=OUTPUT_SCHEMA,
        workspace=workspace,
        readable_paths=(candidate, figure),
        editable_paths=(),
        context_bytes=len(prompt.encode()),
        estimated_input_tokens=200,
        reserved_output_tokens=400,
        reserved_cache_read_tokens=0,
        reserved_cache_write_tokens=0,
        tool_policies={"Read": policy},
        output_validator=_validate_output,
        effort=effort,
    )


def _run_with_required_reads(runtime, request, candidate, figure):
    outcome = runtime.run(request)
    required = {candidate.resolve(), figure.resolve()}
    if _read_paths(outcome) != required:
        outcome = runtime.run(replace(
            request,
            run_id=f"{request.run_id}-native-read-retry",
            prompt=(
                f"{request.prompt}\n\nPROTOCOL REPAIR: the previous response was "
                "discarded. Read each required file exactly once with the "
                "specified full ranges, then return the JSON result."
            ),
        ))
    if _read_paths(outcome) != required:
        raise RuntimeError("figure fidelity reviewer did not read both sources")
    return outcome


def _result(outcome) -> dict[str, object]:
    payload = thaw_json_object(outcome.structured_output)
    raw_decision = payload.get("decision")
    action_normalizations = _normalize_actions(payload.get("issues", ()))
    payload["decision"] = _decision(payload.get("issues", ()))
    return {
        "agent_type": REVIEWER_NAME,
        "is_error": False,
        "payload": payload,
        "decision_normalized": raw_decision != payload["decision"],
        "action_normalizations": action_normalizations,
        "usage": (
            asdict(outcome.record.usage)
            if outcome.record.usage.total_tokens else None
        ),
        "usage_complete": outcome.record.usage_complete,
        "model": outcome.record.model,
        "duration_ms": outcome.record.elapsed_ms,
        "turns": outcome.record.turns,
        "tool_calls": [item.name for item in outcome.record.tool_calls],
    }


def _validate_output(value) -> None:
    issues = value.get("issues", ())
    actions = {
        item.get("repair_action") for item in issues if isinstance(item, dict)
    }
    if not actions <= REPAIR_ACTIONS:
        raise ValueError("invalid figure fidelity repair_action")
    for item in issues:
        if (
            item.get("repair_action") == "auto_repair"
            and item.get("confidence", 0) < 0.85
        ):
            raise ValueError("auto_repair requires confidence >= 0.85")


def _decision(issues) -> str:
    return (
        "needs_repair"
        if any(item.get("repair_action") == "auto_repair" for item in issues)
        else "pass"
    )


def _normalize_actions(issues) -> int:
    changed = 0
    for issue in issues:
        if (
            issue.get("category") == "orientation_change"
            and issue.get("difference_scope") == "base_figure"
            and issue.get("authority_status") == "supported"
            and issue.get("source_role") == "required_input"
            and issue.get("temporal_status")
            == "corresponding_stage_mismatch"
            and issue.get("confidence", 0) >= 0.85
        ):
            issue["semantic_equivalence"] = False
            if issue.get("repair_action") != "auto_repair":
                issue["repair_action"] = "auto_repair"
                changed += 1
        if issue.get("repair_action") != "auto_repair":
            continue
        if issue.get("difference_scope") in {
            "runtime_problem_panel", "later_subquestion_stage", "decorative",
        } or (
            issue.get("semantic_equivalence") is True
            or issue.get("temporal_status") == "delayed_but_present"
        ):
            issue["repair_action"] = "evidence_only"
            changed += 1
        elif issue.get("difference_scope") == "later_solution_content" or (
            issue.get("authority_status") != "supported"
            or issue.get("source_role") != "required_input"
            or issue.get("temporal_status") != "corresponding_stage_mismatch"
        ):
            issue["repair_action"] = "human_review"
            changed += 1
    return changed


def _read_normalizer(workspace, exact_reads):
    def normalize(value):
        requested = Path(str(value.get("file_path") or ""))
        resolved = (
            requested if requested.is_absolute() else workspace / requested
        ).resolve()
        if resolved not in exact_reads:
            raise ValueError("Read path is not a figure fidelity source")
        offset, limit = exact_reads[resolved]
        return {"file_path": str(resolved), "offset": offset, "limit": limit}
    return normalize


def _read_paths(outcome) -> set[Path]:
    return {
        Path(str(item.input.get("file_path"))).resolve()
        for item in outcome.record.tool_calls
        if item.allowed and item.name == "Read" and item.input.get("file_path")
    }


def _figure_plan(figure: Path) -> str:
    path = figure.with_name("figure-plan.json")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))[:12_000]
    except (OSError, ValueError, TypeError):
        return '{"visual_role":"unknown"}'


def _line_count(path: Path) -> int:
    return max(1, len(path.read_text(encoding="utf-8").splitlines()))
