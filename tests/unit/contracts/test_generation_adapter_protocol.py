from __future__ import annotations

import asyncio

from manim_quality.contracts import GenerationAdapter, QualitySubmission


def _submission() -> QualitySubmission:
    return QualitySubmission(
        job_id="job-1",
        tenant_id="tenant-1",
        candidate_code_ref="artifact://candidate.py",
        problem_text="Find x.",
        planning={},
        expected_answer=None,
        render_manifest_ref=None,
        asset_manifest_ref=None,
        callback_url=None,
        idempotency_key="quality:job-1:1",
    )


class FakeGenerationAdapter:
    def __init__(self) -> None:
        self.failure_evidence_ref: str | None = None

    async def regenerate(
        self,
        submission: QualitySubmission,
        failure_evidence_ref: str,
    ) -> QualitySubmission:
        self.failure_evidence_ref = failure_evidence_ref
        return submission


async def _call_adapter(
    adapter: GenerationAdapter,
    submission: QualitySubmission,
) -> QualitySubmission:
    return await adapter.regenerate(submission, "artifact://failure.json")


def test_generation_adapter_is_static_protocol_with_async_fake_behavior() -> None:
    adapter = FakeGenerationAdapter()
    submission = _submission()

    result = asyncio.run(_call_adapter(adapter, submission))

    assert getattr(GenerationAdapter, "_is_runtime_protocol", False) is False
    assert result is submission
    assert adapter.failure_evidence_ref == "artifact://failure.json"
