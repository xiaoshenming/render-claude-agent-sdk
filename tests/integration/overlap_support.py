from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from manim_quality.layout.adapter import OverlapRepairRequest

ROOT = Path(__file__).resolve().parents[2]
VENDOR_ROOT = ROOT / ".vendor" / "quality_repair"
BASE_CODE = """from manim import *

class Lesson(Scene):
    def construct(self):
        label = MathTex(r\"x=1\")
        label.move_to(ORIGIN)
        self.play(Write(label))
"""


def make_request(tmp_path: Path, *, tokens: int = 60_000) -> OverlapRepairRequest:
    code_path = tmp_path / "candidate.py"
    code_path.write_text(BASE_CODE, encoding="utf-8")
    context_path = tmp_path / "layout_context.json"
    context_path.write_text(
        json.dumps(
            {
                "active_visible_objects": [
                    {"path": "label", "class": "MathTex"},
                    {"path": "axis", "class": "Line"},
                ],
                "top_blocking_issues": [{"kind": "overlap", "a": "label", "b": "axis"}],
                "blocking_layout_issue_count": 2,
                "pass": False,
                "status": "layout_failed",
            }
        ),
        encoding="utf-8",
    )
    return OverlapRepairRequest(
        job_id="job-overlap-1",
        code_path=code_path,
        layout_context_path=context_path,
        evidence_root=tmp_path / "evidence",
        remaining_tokens=tokens,
    )


def make_check(api, blocking: int):
    return api.CheckResult(
        ok=True,
        passed=blocking == 0,
        blocking_count=blocking,
        issues=[
            {"kind": "overlap", "a": f"label-{index}", "b": f"axis-{index}"}
            for index in range(blocking)
        ],
    )


def fake_runner(api, code: str, *, tokens: int = 321):
    class Runner:
        def run(self, workdir: Path, prompt: str, budget):
            del prompt, budget
            target = workdir / "core_candidate.py"
            target.write_text(
                code[code.index("class ") :] if target.exists() else code,
                encoding="utf-8",
            )
            return api.AgentRunReport(
                changed=True,
                tokens_used=tokens,
                final_text='{"action":"fix","file":"core_candidate.py"}',
            )

    return Runner()


def vendor_result(
    *,
    status: str,
    candidate: Path,
    before: int,
    after: int,
    tokens: int = 100,
    evidence_dir: Path | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        code_path=candidate,
        before={"blocking_count": before},
        after={"blocking_count": after},
        rounds_used=1,
        tokens_used=tokens,
        cost_usd=0.0,
        evidence_dir=evidence_dir or candidate.parents[1],
        reasons=[],
    )
