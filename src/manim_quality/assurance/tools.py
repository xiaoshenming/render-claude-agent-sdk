from __future__ import annotations

import ast
import hashlib
import json
import subprocess
from pathlib import Path

from .lifecycle_evidence import detached_transition_parts
from .models import AssuranceCase, ToolReport


def inspect_artifact(case: AssuranceCase) -> ToolReport:
    if not case.video_path.is_file() or case.video_path.stat().st_size == 0:
        return _report("inspect_artifact", "incomplete", ("missing_video",))
    probe = _ffprobe(case.video_path)
    risks = []
    if probe.get("returncode") != 0:
        risks.append("ffprobe_failed")
    elif not probe.get("video"):
        risks.append("missing_video_stream")
    evidence = {
        "id": f"{case.key}:artifact",
        "path": str(case.video_path),
        "sha256": _sha256(case.video_path),
        **probe,
    }
    risks = list(risks)
    if (
        case.expected_video_sha256
        and evidence["sha256"] != case.expected_video_sha256
    ):
        risks.append("final_video_sha_mismatch")
    return _report(
        "inspect_artifact",
        "risk" if risks else "complete",
        tuple(risks),
        evidence,
    )


def inspect_execution(case: AssuranceCase) -> ToolReport:
    summary = _json(case.log_dir / "run_summary.json")
    risks = []
    if not summary:
        risks.append("missing_run_summary")
    if summary.get("decision") != "PROPOSED":
        risks.append("quality_not_proposed")
    if not summary.get("final_revision_id"):
        risks.append("missing_final_revision")
    return _report(
        "inspect_execution",
        "risk" if risks else "complete",
        tuple(risks),
        {"id": f"{case.key}:execution", **summary},
    )


def inspect_code_review(case: AssuranceCase) -> ToolReport:
    source_evidence, source_risks = _inspect_source(case)
    findings = (
        ()
        if source_evidence
        else _findings(case, {"logic", "lifecycle", "code"})
    )
    risks = list(source_risks)
    if _blocking(findings):
        risks.append("blocking_logic_finding")
    return _report(
        "inspect_code_review",
        "risk" if risks else ("complete" if source_evidence else "incomplete"),
        tuple(risks),
        *source_evidence,
        *findings,
    )


def inspect_layout(case: AssuranceCase) -> ToolReport:
    lifecycle = detached_transition_parts(case.source_path)
    prior = _json(case.log_dir / "layout_evidence.json")
    if prior:
        evidence = {
            "id": f"{case.key}:quality-layout",
            "source": "quality_agent_reused_bbox",
            **prior,
            "lifecycle_findings": list(lifecycle),
        }
        if not prior.get("verified") or prior.get("error"):
            return _report(
                "inspect_layout", "incomplete", ("quality_layout_unverified",),
                evidence,
            )
        blocking = int(prior.get("blocking_count") or 0)
        risks = []
        if blocking:
            risks.append("blocking_layout_finding")
        if lifecycle:
            risks.append("detached_transition_part")
        return _report(
            "inspect_layout",
            "risk" if risks else "complete",
            tuple(risks),
            evidence,
        )
    findings = _findings(case, {"layout", "overlap", "bbox"})
    risks = []
    if _blocking(findings):
        risks.append("blocking_layout_finding")
    if lifecycle:
        risks.append("detached_transition_part")
    evidence = ({
        "id": f"{case.key}:lifecycle-layout",
        "lifecycle_findings": list(lifecycle),
    },) if lifecycle else ()
    return _report(
        "inspect_layout",
        "risk" if risks else ("complete" if findings else "incomplete"),
        tuple(risks),
        *evidence,
        *findings,
    )


def inspect_consistency(case: AssuranceCase) -> ToolReport:
    summary = _json(case.log_dir / "run_summary.json")
    result = _json(case.log_dir / "result.json")
    final = summary.get("final_revision_id")
    logic = result.get("logic") if isinstance(result.get("logic"), dict) else {}
    reported = logic.get("final_revision_id")
    risks = []
    if final and reported and final != reported:
        risks.append("revision_identity_mismatch")
    if result.get("status") == "deliver_with_warning":
        risks.append("delivered_with_warning")
    source_sha = (
        _sha256(case.source_path)
        if case.source_path is not None and case.source_path.is_file()
        else None
    )
    return _report(
        "inspect_consistency",
        "risk" if risks else "complete",
        tuple(risks),
        {
            "id": f"{case.key}:consistency",
            "run_final_revision": final,
            "result_final_revision": reported,
            "delivery_revision_id": case.delivery_revision_id,
            "local_verification_revision": "R0",
            "local_revision_is_delivery_alias": case.source_path is not None,
            "delivery_source_sha256": source_sha,
        },
    )


def _findings(case: AssuranceCase, categories: set[str]) -> tuple[dict, ...]:
    rows = _json(case.log_dir / "findings.json").get("findings", [])
    if not isinstance(rows, list):
        return ()
    return tuple(
        {"id": f"{case.key}:{row.get('finding_id', 'finding')}", **row}
        for row in rows
        if isinstance(row, dict) and str(row.get("category", "")).lower() in categories
    )


def _blocking(rows: tuple[dict, ...]) -> bool:
    return any(row.get("severity") in {"blocking", "critical", "high"} for row in rows)


def _inspect_source(case: AssuranceCase) -> tuple[tuple[dict, ...], tuple[str, ...]]:
    if case.source_path is None or not case.source_path.is_file():
        return (), ()
    text = case.source_path.read_text(encoding="utf-8")
    risks = []
    tree = None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        risks.append("final_source_syntax_error")
    derived_mismatches = (
        _derived_parameter_mismatches(tree) if tree is not None else ()
    )
    if derived_mismatches:
        risks.append("derived_function_parameter_mismatch")
    evidence = {
        "id": f"{case.key}:final-source",
        "path": str(case.source_path),
        "sha256": _sha256(case.source_path),
        "lines": text.count("\n") + 1,
        "voiceover_blocks": text.count("voiceover("),
        "ast_parse_ok": tree is not None,
        "derived_parameter_mismatches": list(derived_mismatches),
    }
    return (evidence,), tuple(risks)


def _derived_parameter_mismatches(tree: ast.AST) -> tuple[dict, ...]:
    """Find numeric helper calls where ``ab_val`` differs from ``a_val*b_val``."""
    signatures = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = [item.arg for item in node.args.args]
        signatures[node.name] = names

    mismatches = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        names = signatures.get(node.func.id)
        if not names:
            continue
        values = {
            name: _numeric_literal(value)
            for name, value in zip(names, node.args, strict=False)
        }
        for derived in names:
            if not derived.endswith("_val"):
                continue
            symbol = derived.removesuffix("_val")
            if len(symbol) != 2:
                continue
            left, right = f"{symbol[0]}_val", f"{symbol[1]}_val"
            actual = values.get(derived)
            left_value, right_value = values.get(left), values.get(right)
            if actual is None or left_value is None or right_value is None:
                continue
            expected = left_value * right_value
            if abs(actual - expected) <= 1e-9:
                continue
            mismatches.append(
                {
                    "line": node.lineno,
                    "helper": node.func.id,
                    "parameter": derived,
                    "expression": f"{left} * {right}",
                    "expected": expected,
                    "actual": actual,
                }
            )
    return tuple(mismatches)


def _numeric_literal(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.USub, ast.UAdd))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        value = float(node.operand.value)
        return -value if isinstance(node.op, ast.USub) else value
    return None


def _report(tool: str, status: str, risks: tuple[str, ...], *evidence) -> ToolReport:
    return ToolReport(tool, status, risks, tuple(evidence))


def _json(path: Path) -> dict:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ffprobe(path: Path) -> dict[str, object]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
    value = json.loads(completed.stdout or "{}") if completed.returncode == 0 else {}
    streams = value.get("streams", []) if isinstance(value, dict) else []
    return {
        "returncode": completed.returncode,
        "duration": (value.get("format") or {}).get("duration"),
        "video": any(row.get("codec_type") == "video" for row in streams),
        "audio": any(row.get("codec_type") == "audio" for row in streams),
    }
