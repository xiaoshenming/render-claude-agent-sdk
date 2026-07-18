import json
from pathlib import Path
from typing import cast

from manim_quality.agents.budget import BudgetLimits
from manim_quality.agents.profile import reviewer_profile
from manim_quality.agents.runtime import (
    AgentBackend,
    AgentRuntime,
    BackendRequest,
    BackendResult,
    RuntimeControls,
)
from manim_quality.agents.usage import AgentCallRecord, TokenUsage, UsageSink
from manim_quality.contracts import (
    PatchScope,
    QualitySubmission,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.geometry.schemas import GeometrySnapshot
from manim_quality.logic.engine_adapter import build_engine_review_evidence
from manim_quality.logic.evidence import build_logic_evidence
from manim_quality.logic.review_input import ReviewInputVersion
from manim_quality.logic.reviewer import LogicReviewer
from manim_quality.revisions.fingerprint import (
    code_hash,
    evidence_hash,
    semantic_fingerprint,
)

CODE = """from manim import *

class Scene_02_Solve(Scene):
    def construct(self):
        answer = MathTex("x=12")
        self.add(answer)
"""


class MemorySink(UsageSink):
    def __init__(self) -> None:
        self.records: list[AgentCallRecord] = []

    def save(self, record: AgentCallRecord) -> None:
        self.records.append(record)


class PayloadBackend(AgentBackend):
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.requests: list[BackendRequest] = []

    def run(self, request: BackendRequest, controls: RuntimeControls) -> BackendResult:
        self.requests.append(request)
        controls.record_round_usage(TokenUsage(input_tokens=120, output_tokens=30))
        read_input = {"file_path": request.readable_paths[0]}
        if request.read_tools:
            read_input.update({"offset": 1, "limit": 100})
        controls.authorize_tool("Read", read_input)
        return controls.complete(self.payload)


def limits() -> BudgetLimits:
    return BudgetLimits(
        max_context_bytes=100_000,
        max_turns=1,
        max_tool_calls=4,
        max_elapsed_ms=10_000,
        max_input_tokens=10_000,
        max_output_tokens=2_000,
        max_cache_read_tokens=10_000,
        max_cache_write_tokens=10_000,
        max_total_tokens=20_000,
    )


def setup_evidence(
    tmp_path: Path,
    *,
    expected_answer: str | None = "x=10",
    code: str = CODE,
):
    candidate = tmp_path / "candidate.py"
    candidate.write_text(code, encoding="utf-8")
    manifest = tmp_path / "render_manifest.json"
    manifest.write_text(
        json.dumps({"scenes": ["Scene_02_Solve"], "status": "rendered"}),
        encoding="utf-8",
    )
    (tmp_path / "problem_text.txt").write_text("解方程 x+2=12。", encoding="utf-8")
    manifest_bytes = manifest.read_bytes()
    submission = QualitySubmission(
        job_id="job-1",
        tenant_id="tenant-1",
        candidate_code_ref="candidate.py",
        problem_text="解方程 x+2=12。",
        planning={"method": "两边减 2"},
        expected_answer=expected_answer,
        render_manifest_ref="render_manifest.json",
        asset_manifest_ref=None,
        callback_url=None,
        idempotency_key="idem-1",
    )
    revision = Revision(
        revision_id="rev-1",
        parent_revision_id=None,
        stage=RevisionStage.BASELINE,
        code_hash=code_hash(code),
        semantic_fingerprint=semantic_fingerprint(code),
        scene_hashes={},
        render_manifest_hash=evidence_hash(manifest_bytes),
        changed_scene_ids=(),
        patch_scope=PatchScope.FULL_CANDIDATE,
        created_by=RevisionCreator.GENERATION_ADAPTER,
        attempt=0,
    )
    evidence = build_logic_evidence(
        code=code,
        submission=submission,
        revision=revision,
        render_manifest=manifest_bytes,
        engine_evidence=build_engine_review_evidence(tmp_path),
    )
    return candidate, manifest, evidence


def issue_payload(*, excerpt: str = 'MathTex("x=12")') -> dict[str, object]:
    return {
        "decision": "needs_repair",
        "blocked": True,
        "requires_human_review": False,
        "summary": "最终答案与题目证据不一致",
        "review_gaps": [],
        "issues": [
            {
                "issue_id": "issue-1",
                "issue_type": "final_answer_mismatch",
                "severity": "high",
                "confidence": 0.96,
                "repairable": True,
                "repair_scope": "scene_logic",
                "target_scene_ids": ["Scene_02_Solve"],
                "expected": "x=10",
                "observed": "x=12",
                "acceptance_predicates": [{"kind": "text_absent", "value": "x=12"}],
                "non_goals": ["layout"],
                "candidate_evidence": [
                    {
                        "artifact": "candidate_code",
                        "scene_id": "Scene_02_Solve",
                        "line_start": 5,
                        "line_end": 5,
                        "excerpt": excerpt,
                    }
                ],
                "expected_evidence": [
                    {
                        "artifact": "expected_answer",
                        "scene_id": None,
                        "line_start": None,
                        "line_end": None,
                        "excerpt": "x=10",
                    }
                ],
                "supporting_evidence": [],
            }
        ],
    }


def add_citation(payload: dict[str, object], *, artifact: str, excerpt: str) -> None:
    issues = cast(list[dict[str, object]], payload["issues"])
    field = (
        "expected_evidence"
        if artifact in {"problem_text", "planning", "expected_answer"}
        else "supporting_evidence"
    )
    citations = cast(list[dict[str, object]], issues[0][field])
    citations.append(
        {
            "artifact": artifact,
            "scene_id": None,
            "line_start": None,
            "line_end": None,
            "excerpt": excerpt,
        }
    )


def candidate_citation(payload: dict[str, object]) -> dict[str, object]:
    return cast(list[dict[str, object]], issue_entry(payload)["candidate_evidence"])[0]


def issue_entry(payload: dict[str, object]) -> dict[str, object]:
    return cast(list[dict[str, object]], payload["issues"])[0]


def reviewer(
    tmp_path: Path,
    payload: dict[str, object],
    *,
    input_version: ReviewInputVersion = ReviewInputVersion.EVIDENCE_V1,
    geometry_snapshot: GeometrySnapshot | None = None,
):
    backend = PayloadBackend(payload)
    sink = MemorySink()
    runtime = AgentRuntime(backend, sink, limits())
    reviewer_service = LogicReviewer(
        runtime=runtime,
        profile=reviewer_profile(model="fake-model", prompt_version="logic-v1"),
        input_version=input_version,
    )
    candidate, manifest, evidence = setup_evidence(tmp_path)
    result = reviewer_service.review(
        run_id="review-1",
        evidence=evidence,
        workspace=tmp_path,
        candidate_path=candidate,
        render_manifest_path=manifest,
        estimated_input_tokens=500,
        reserved_output_tokens=300,
        geometry_snapshot=geometry_snapshot,
    )
    return result, backend, sink


def service(backend: PayloadBackend) -> LogicReviewer:
    return LogicReviewer(
        runtime=AgentRuntime(backend, MemorySink(), limits()),
        profile=reviewer_profile(model="fake-model", prompt_version="logic-v1"),
    )
