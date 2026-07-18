from __future__ import annotations

import csv
import html
import json
from collections import Counter
from pathlib import Path


def build_report(root: Path) -> dict:
    cases = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("round-*/*/job_summary.json"))
    ]
    statuses = Counter(str(case.get("status")) for case in cases)
    total_tokens = sum(_job_tokens(case) for case in cases)
    strict = statuses["deliver"]
    warnings = statuses["deliver_with_warning"]
    report = {
        "schema_version": "manim-quality.workbench-report.v1",
        "job_count": len(cases),
        "status_counts": dict(statuses),
        "delivery_count": strict,
        "strict_delivery_count": strict,
        "warning_release_count": warnings,
        "quality_release_count": strict + warnings,
        "total_tokens": total_tokens,
        "average_tokens": round(total_tokens / len(cases), 2) if cases else 0,
        "cases": cases,
    }
    (root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(root / "report.csv", cases)
    (root / "before_after.html").write_text(_html(root, cases), encoding="utf-8")
    return report


def _job_tokens(case: dict) -> int:
    generation = case.get("generation") or {}
    logic = case.get("logic") or {}
    layout = case.get("layout") or {}
    return (
        int(generation.get("total_tokens") or 0)
        + int(logic.get("review_tokens") or 0)
        + int(logic.get("repair_tokens") or 0)
        + int(layout.get("tokens") or 0)
    )


def _write_csv(path: Path, cases: list[dict]) -> None:
    fields = ["slot_id", "round_id", "task_id", "status", "elapsed_ms", "tokens"]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    **{key: case.get(key) for key in fields[:-1]},
                    "tokens": _job_tokens(case),
                }
            )


def _html(root: Path, cases: list[dict]) -> str:
    rows = []
    for case in cases:
        job = root / f"round-{case['round_id']}" / case["slot_id"]
        before = _reported_video(root, case, "baseline_render")
        if before is None:
            before = _relative_video(job, "render_baseline")
        after = job / "video_final.mp4"
        rows.append(
            "<article><h2>{slot} · {task} · {status}</h2>"
            "<div><section><h3>Before</h3>{before}</section>"
            "<section><h3>After</h3>{after}</section></div>"
            "<p>Tokens: {tokens} · Time: {elapsed:.1f}s</p></article>".format(
                slot=html.escape(case["slot_id"]),
                task=html.escape(case["task_id"]),
                status=html.escape(case["status"]),
                before=_video_tag(root, before),
                after=_video_tag(root, after if after.is_file() else None),
                tokens=_job_tokens(case),
                elapsed=float(case.get("elapsed_ms", 0)) / 1_000,
            )
        )
    head = """<!doctype html><meta charset='utf-8'><title>Workbench E2E</title>
<style>
body{font:14px Arial;margin:24px;background:#f4f5f7;color:#17191c}
article{background:#fff;border:1px solid #d8dce2;padding:16px;
margin:16px 0;border-radius:6px}
article>div{display:grid;grid-template-columns:1fr 1fr;gap:16px}
video{width:100%;max-height:480px;background:#111}
h2{font-size:18px}h3{font-size:14px}
@media(max-width:800px){article>div{grid-template-columns:1fr}}
</style>"""
    return head + "".join(rows)


def _relative_video(job: Path, render_name: str) -> Path | None:
    matches = list((job / render_name).rglob("result.mp4"))
    return matches[-1] if matches else None


def _reported_video(root: Path, case: dict, field: str) -> Path | None:
    section = case.get(field)
    raw = section.get("video_path") if isinstance(section, dict) else None
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw).resolve()
    allowed = root.resolve()
    return path if path.is_file() and path.is_relative_to(allowed) else None


def _video_tag(root: Path, path: Path | None) -> str:
    if path is None:
        return "<p>No video</p>"
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return f"<video controls preload='metadata' src='{html.escape(relative)}'></video>"
