from __future__ import annotations

from dataclasses import replace

from pathlib import Path

import pytest

from manim_quality.rendering.impact import analyze_source

from manim_quality.rendering.interfaces import (
    ArtifactResult,
    CommandResult,
    EnvironmentEvidence,
    RenderFailureStage,
    RenderRequest,
)

from manim_quality.rendering.manim_adapter import ManimRenderAdapter

from manim_quality.rendering.slices import CertifiedSlice, scene_order_hash

from manim_quality.revisions.fingerprint import sha256_bytes, sha256_text

from manim_quality.storage import ArtifactRef

class FakeRenderer:
    def __init__(
        self, *, fail: str | None = None, mutate_path: Path | None = None
    ) -> None:
        self.fail = fail
        self.mutate_path = mutate_path
        self.calls: list[tuple[str, object]] = []

    def compile(self, request: RenderRequest) -> CommandResult:
        self.calls.append(("compile", request.revision_id))
        return CommandResult(self.fail != "compile", "compile failed")

    def render_scene(self, request: RenderRequest, scene_id: str) -> ArtifactResult:
        self.calls.append(("render", scene_id))
        if self.fail == scene_id:
            return ArtifactResult.failure(f"{scene_id} failed")
        return ArtifactResult.success(_artifact(f"rendered:{scene_id}"))

    def concatenate(
        self, request: RenderRequest, slices: tuple[ArtifactRef, ...]
    ) -> ArtifactResult:
        self.calls.append(("concat", tuple(item.hash for item in slices)))
        if self.mutate_path is not None:
            self.mutate_path.write_text("tampered = True\n", encoding="utf-8")
        if self.fail == "concat":
            return ArtifactResult.failure("concat failed")
        return ArtifactResult.success(_artifact("final-video"))

class MemoryArtifactStore:
    def __init__(self, *, corrupt_hash: str | None = None) -> None:
        self.corrupt_hash = corrupt_hash

    def get(self, artifact: ArtifactRef) -> bytes:
        if artifact.hash == self.corrupt_hash:
            return b"corrupt"
        for label in _ARTIFACT_LABELS:
            content = label.encode()
            if sha256_bytes(content) == artifact.hash:
                return content
        raise KeyError(artifact.hash)

    def put(
        self,
        content: bytes,
        *,
        media_type: str,
        expected_hash: str | None = None,
    ) -> ArtifactRef:
        del expected_hash
        return _artifact(content.decode(), media_type=media_type)

class FakeCertificationAuthority:
    def __init__(self, *, reject_scene: str | None = None) -> None:
        self.reject_scene = reject_scene
        self.calls: list[str] = []

    def authorize_reuse(self, item: CertifiedSlice) -> bool:
        self.calls.append(item.scene_id)
        return (
            item.scene_id != self.reject_scene
            and item.source_revision_id == "rev-1"
            and item.source_manifest_hash == sha256_text("manifest-v1")
            and item.certification_hash == sha256_text("certificate-v1")
        )

class FakeEnvironmentAuthority:
    def __init__(
        self,
        *,
        complete: bool = True,
        uncertain: bool = False,
        assets_hash: str | None = None,
        error: bool = False,
        invalid: bool = False,
    ) -> None:
        self.complete = complete
        self.uncertain = uncertain
        self.assets_hash = assets_hash or sha256_text("assets-v1")
        self.error = error
        self.invalid = invalid

    def resolve_environment(self, request: RenderRequest) -> EnvironmentEvidence:
        del request
        if self.error:
            raise RuntimeError("environment unavailable")
        if self.invalid:
            return object()  # type: ignore[return-value]
        return EnvironmentEvidence(
            assets_hash=self.assets_hash,
            external_dependencies_hash=sha256_text("external-v1"),
            complete=self.complete,
            uncertain=self.uncertain,
            evidence_hash=sha256_text("environment-evidence-v1"),
            version="environment-v1",
        )

def _request(
    tmp_path: Path,
    *,
    certify_proof: bool = False,
    source: str | None = None,
    ordered_scene_ids: tuple[str, ...] = ("Intro", "Proof"),
) -> RenderRequest:
    del tmp_path
    source = source or _source()
    impact = analyze_source(source, ordered_scene_ids)
    first_scene = ordered_scene_ids[0]
    certified = {
        first_scene: _certified_slice(
            first_scene,
            impact.scene_hashes[first_scene],
            impact.shared_dependency_hash,
            "intro",
            ordered_scene_ids,
        )
    }
    if certify_proof and "Proof" in ordered_scene_ids:
        certified["Proof"] = _certified_slice(
            "Proof",
            impact.scene_hashes["Proof"],
            impact.shared_dependency_hash,
            "old-proof",
            ordered_scene_ids,
        )
    return RenderRequest(
        revision_id="rev-2",
        source_code=source,
        code_hash=sha256_text(source),
        scene_hashes=impact.scene_hashes,
        ordered_scene_ids=ordered_scene_ids,
        certified_slices=certified,
        render_config_hash=sha256_text("1080p30"),
        renderer_version="manim-0.19",
        assets_hash=sha256_text("assets-v1"),
    )

def _certified_slice(
    scene_id: str,
    scene_hash: str,
    shared_hash: str,
    label: str,
    ordered_scene_ids: tuple[str, ...] = ("Intro", "Proof"),
) -> CertifiedSlice:
    return CertifiedSlice(
        scene_id=scene_id,
        scene_hash=scene_hash,
        artifact=_artifact(label),
        source_revision_id="rev-1",
        source_manifest_hash=sha256_text("manifest-v1"),
        certification_hash=sha256_text("certificate-v1"),
        render_config_hash=sha256_text("1080p30"),
        renderer_version="manim-0.19",
        assets_hash=sha256_text("assets-v1"),
        scene_order_hash=scene_order_hash(ordered_scene_ids),
        shared_dependency_hash=shared_hash,
        external_dependencies_hash=sha256_text("external-v1"),
        environment_evidence_hash=sha256_text("environment-evidence-v1"),
        environment_version="environment-v1",
    )

def _adapter(
    renderer: FakeRenderer,
    *,
    authority: FakeCertificationAuthority | None = None,
    environment: FakeEnvironmentAuthority | None = None,
) -> ManimRenderAdapter:
    return ManimRenderAdapter(
        renderer,
        MemoryArtifactStore(),
        authority or FakeCertificationAuthority(),
        environment or FakeEnvironmentAuthority(),
    )

def _artifact(label: str, *, media_type: str = "video/mp4") -> ArtifactRef:
    content = label.encode()
    return ArtifactRef(
        uri=f"memory://{label}",
        hash=sha256_bytes(content),
        size=len(content),
        media_type=media_type,
    )

def _source() -> str:
    return """from manim import Scene

SCALE = 1

def helper(value):
    return value * SCALE

class Intro(Scene):
    def construct(self):
        self.value = helper(1)

class Proof(Scene):
    def construct(self):
        self.value = helper(2)
"""

def _source_with_base(body: str) -> str:
    return f"""from manim import Scene

class BaseScene(Scene):
    def helper(self):
        {body}

class Lesson(BaseScene):
    def construct(self):
        self.value = self.helper()
"""

_ARTIFACT_LABELS = (
    "intro",
    "old-proof",
    "rendered:Intro",
    "rendered:Proof",
    "rendered:Lesson",
    "final-video",
)
