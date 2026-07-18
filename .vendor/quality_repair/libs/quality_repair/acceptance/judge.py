"""quality_repair.acceptance.judge — 六态判定，agent 进程外唯一裁判入口。

pass/fail 只由 CheckerAdapter（外层确定性 checker）判定；本文件只做门禁编排
与状态映射，不引入任何新的"判对判错"来源。任何内部异常在 judge() 边界兜底为
REVIEW_ERROR，不上抛给调用方。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..interfaces import CheckerAdapter, RendererAdapter
from ..schemas import AcceptanceReport, CheckResult
from ..statuses import (
    REPAIR_FAILED,
    REPAIR_UNCHANGED,
    REPAIR_WORSE,
    REVIEW_ERROR,
    SUCCESS_CLEAN,
    SUCCESS_DEGRADED,
)

GATE_NAMES: tuple[str, ...] = ("compile", "recheck", "render", "bbox_guard", "diff_audit")
SAFETY_GATES: tuple[str, ...] = ("render", "bbox_guard", "diff_audit")
_BBOX_AXES: tuple[str, ...] = ("x", "y", "z")


def judge(
    *,
    workdir: Path,
    input_code: str,
    output_code: str,
    before: CheckResult,
    checker: CheckerAdapter,
    renderer: RendererAdapter | None = None,
    protected: dict[str, Any] | None = None,
    safe_area: dict[str, Any] | None = None,
    scene_names: list[str] | None = None,
) -> AcceptanceReport:
    """六态验收判定。任何内部异常都在此边界兜底为 REVIEW_ERROR，不上抛。"""
    try:
        return _judge_impl(
            workdir=workdir,
            input_code=input_code,
            output_code=output_code,
            before=before,
            checker=checker,
            renderer=renderer,
            protected=protected,
            safe_area=safe_area,
            scene_names=scene_names,
        )
    except Exception as exc:  # noqa: BLE001 — 层边界，fail-open 红线要求捕获
        return AcceptanceReport(status=REVIEW_ERROR, reasons=[f"judge_error:{exc}"])


def _judge_impl(
    *,
    workdir: Path,
    input_code: str,
    output_code: str,
    before: CheckResult,
    checker: CheckerAdapter,
    renderer: RendererAdapter | None,
    protected: dict[str, Any] | None,
    safe_area: dict[str, Any] | None,
    scene_names: list[str] | None,
) -> AcceptanceReport:
    if output_code == input_code:
        return AcceptanceReport(
            status=REPAIR_UNCHANGED,
            gates={name: "skip" for name in GATE_NAMES},
            reasons=["output_identical_to_input"],
            before=_check_summary(before),
            after=_check_summary(before),
        )

    gates: dict[str, str] = {}
    reasons: list[str] = []

    _gate_compile(output_code, gates, reasons)
    after = _gate_recheck(
        output_code=output_code, workdir=workdir, checker=checker, gates=gates, reasons=reasons
    )
    _gate_render(
        renderer=renderer, scene_names=scene_names, workdir=workdir, gates=gates, reasons=reasons
    )
    _gate_bbox(after=after, safe_area=safe_area, gates=gates, reasons=reasons)
    _gate_diff_audit(
        input_code=input_code, output_code=output_code, protected=protected,
        gates=gates, reasons=reasons,
    )

    status = _map_status(before=before, after=after, gates=gates)
    return AcceptanceReport(
        status=status,
        gates=gates,
        reasons=reasons,
        before=_check_summary(before),
        after=_check_summary(after),
    )


def _gate_compile(output_code: str, gates: dict[str, str], reasons: list[str]) -> None:
    try:
        compile(output_code, "candidate.py", "exec")
        gates["compile"] = "pass"
    except SyntaxError as exc:
        gates["compile"] = "fail"
        reasons.append(f"compile_syntax_error:{exc}")


def _gate_recheck(
    *,
    output_code: str,
    workdir: Path,
    checker: CheckerAdapter,
    gates: dict[str, str],
    reasons: list[str],
) -> CheckResult:
    candidate_path = workdir / "candidate.py"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text(output_code, encoding="utf-8")
    after = checker.run_check(candidate_path, workdir)
    if not after.ok:
        gates["recheck"] = "error"
        reasons.append(f"recheck_error:{after.error or 'checker_not_ok'}")
    else:
        gates["recheck"] = "pass"
    return after


def _gate_render(
    *,
    renderer: RendererAdapter | None,
    scene_names: list[str] | None,
    workdir: Path,
    gates: dict[str, str],
    reasons: list[str],
) -> None:
    if renderer is None or not scene_names:
        gates["render"] = "skip"
        return
    candidate_path = workdir / "candidate.py"
    failures: list[str] = []
    for scene in scene_names:
        out_dir = workdir / "_acceptance_render" / scene
        result = renderer.render_scene(candidate_path, scene, out_dir)
        if not result.ok:
            failures.append(scene)
    if failures:
        gates["render"] = "fail"
        reasons.append("render_failed:" + ",".join(failures))
    else:
        gates["render"] = "pass"


def _gate_bbox(
    *,
    after: CheckResult,
    safe_area: dict[str, Any] | None,
    gates: dict[str, str],
    reasons: list[str],
) -> None:
    if not safe_area:
        gates["bbox_guard"] = "skip"
        return
    bbox_dicts = _collect_bbox_dicts(after)
    if not bbox_dicts:
        gates["bbox_guard"] = "skip"
        return
    exploded: list[str] = []
    for bbox in bbox_dicts:
        exploded.extend(_bbox_violations(bbox, safe_area))
    if exploded:
        gates["bbox_guard"] = "fail"
        reasons.append("bbox_explosion:" + ",".join(exploded))
    else:
        gates["bbox_guard"] = "pass"


def _gate_diff_audit(
    *,
    input_code: str,
    output_code: str,
    protected: dict[str, Any] | None,
    gates: dict[str, str],
    reasons: list[str],
) -> None:
    if protected is None:
        gates["diff_audit"] = "skip"
        return
    violations: list[str] = []
    for pattern in protected.get("forbidden_patterns", []):
        if input_code.count(pattern) != output_code.count(pattern):
            violations.append(f"forbidden_pattern_changed:{pattern}")
    if protected.get("protect_string_literals"):
        missing = _string_literals(input_code) - _string_literals(output_code)
        if missing:
            violations.append(f"string_literal_removed:{sorted(missing)[:5]}")
    if violations:
        gates["diff_audit"] = "fail"
        reasons.extend(violations)
    else:
        gates["diff_audit"] = "pass"


def _map_status(*, before: CheckResult, after: CheckResult, gates: dict[str, str]) -> str:
    if "error" in gates.values():
        return REVIEW_ERROR
    if gates.get("compile") == "fail":
        return REPAIR_WORSE
    safety_failed = any(gates.get(name) == "fail" for name in SAFETY_GATES)
    if after.blocking_count > before.blocking_count or safety_failed:
        return REPAIR_WORSE
    all_pass = all(status == "pass" for status in gates.values() if status != "skip")
    if after.blocking_count == 0 and all_pass:
        return SUCCESS_CLEAN
    safety_ok = all(gates.get(name, "skip") in ("pass", "skip") for name in SAFETY_GATES)
    if before.blocking_count > after.blocking_count > 0 and safety_ok:
        return SUCCESS_DEGRADED
    return REPAIR_FAILED


def _check_summary(check: CheckResult) -> dict[str, Any]:
    return {
        "blocking_count": check.blocking_count,
        "passed": check.passed,
        "signature": check.signature,
    }


def _collect_bbox_dicts(check: CheckResult) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for issue in check.issues:
        bbox = issue.get("bbox")
        if isinstance(bbox, dict):
            found.append(bbox)
    raw = check.raw if isinstance(check.raw, dict) else {}
    raw_bboxes = raw.get("bboxes")
    if isinstance(raw_bboxes, list):
        found.extend(b for b in raw_bboxes if isinstance(b, dict))
    raw_bbox = raw.get("bbox")
    if isinstance(raw_bbox, dict):
        found.append(raw_bbox)
    return found


def _bbox_violations(bbox: dict[str, Any], safe_area: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for axis in _BBOX_AXES:
        bound = max(
            abs(_as_float(safe_area.get(f"{axis}_min"))),
            abs(_as_float(safe_area.get(f"{axis}_max"))),
        )
        if bound <= 0:
            continue
        for key in (axis, f"{axis}_min", f"{axis}_max"):
            value = bbox.get(key)
            if value is None:
                continue
            if abs(_as_float(value)) > bound * 2.0:
                violations.append(f"{key}={value}")
    return violations


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _string_literals(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip()
    }
