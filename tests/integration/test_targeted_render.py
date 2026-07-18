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


def test_targeted_render_reuses_only_unchanged_certified_slices(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    renderer = FakeRenderer()

    result = _adapter(renderer).render(request)

    assert result.succeeded is True
    assert renderer.calls[:2] == [("compile", "rev-2"), ("render", "Proof")]
    assert [item.scene_id for item in result.manifest.slices] == ["Intro", "Proof"]
    assert (
        result.manifest.slices[0].artifact == request.certified_slices["Intro"].artifact
    )
    assert result.manifest.slices[0].reused is True
    assert result.manifest.slices[1].reused is False
    assert renderer.calls[-1][0] == "concat"


def test_shared_helper_change_forces_full_rerender(tmp_path: Path) -> None:
    request = _request(tmp_path)
    source = request.source_code.replace("SCALE = 1", "SCALE = 2")
    impact = analyze_source(source, request.ordered_scene_ids)
    request = replace(
        request,
        source_code=source,
        code_hash=sha256_text(source),
        scene_hashes=impact.scene_hashes,
    )
    renderer = FakeRenderer()

    result = _adapter(renderer).render(request)

    assert result.succeeded is True
    assert result.plan.full_rerender is True
    assert result.plan.render_scene_ids == ("Intro", "Proof")
    assert [call for call in renderer.calls if call[0] == "render"] == [
        ("render", "Intro"),
        ("render", "Proof"),
    ]
    assert all(not item.reused for item in result.manifest.slices)


def test_base_scene_change_forces_full_rerender(tmp_path: Path) -> None:
    source = _source_with_base("return 1")
    request = _request(tmp_path, source=source, ordered_scene_ids=("Lesson",))
    changed = _source_with_base("return 2")
    impact = analyze_source(changed, request.ordered_scene_ids)
    request = replace(
        request,
        source_code=changed,
        code_hash=sha256_text(changed),
        scene_hashes=impact.scene_hashes,
    )

    result = _adapter(FakeRenderer()).render(request)

    assert result.succeeded is True
    assert result.plan.full_rerender is True
    assert result.plan.render_scene_ids == ("Lesson",)
    assert "shared_dependency_changed" in result.plan.full_rerender_reasons


def test_forged_scene_hashes_fail_closed(tmp_path: Path) -> None:
    request = _request(tmp_path)
    forged = dict(request.scene_hashes)
    forged["Proof"] = sha256_text("forged")

    result = _adapter(FakeRenderer()).render(replace(request, scene_hashes=forged))

    assert result.succeeded is False
    assert result.failure_stage is RenderFailureStage.IMPACT_ANALYSIS


def test_incomplete_environment_forces_full_rerender(tmp_path: Path) -> None:
    environment = FakeEnvironmentAuthority(complete=False, uncertain=True)

    result = _adapter(FakeRenderer(), environment=environment).render(
        _request(tmp_path)
    )

    assert result.succeeded is True
    assert result.plan.full_rerender is True
    assert result.plan.render_scene_ids == ("Intro", "Proof")
    assert "environment_uncertain" in result.plan.full_rerender_reasons


@pytest.mark.parametrize("mode", ["error", "invalid", "asset_mismatch"])
def test_environment_authority_failures_are_fail_closed(
    tmp_path: Path, mode: str
) -> None:
    environment = FakeEnvironmentAuthority(
        error=mode == "error",
        invalid=mode == "invalid",
        assets_hash=sha256_text("wrong-assets") if mode == "asset_mismatch" else None,
    )

    result = _adapter(FakeRenderer(), environment=environment).render(
        _request(tmp_path)
    )

    assert result.succeeded is False
    assert result.failure_stage is RenderFailureStage.ENVIRONMENT


@pytest.mark.parametrize(
    ("failure", "stage", "expected_calls"),
    [
        ("compile", RenderFailureStage.COMPILE, ["compile"]),
        ("Proof", RenderFailureStage.SCENE_RENDER, ["compile", "render"]),
        ("concat", RenderFailureStage.CONCATENATE, ["compile", "render", "concat"]),
    ],
)
def test_render_failures_are_fail_closed_and_never_continue(
    tmp_path: Path,
    failure: str,
    stage: RenderFailureStage,
    expected_calls: list[str],
) -> None:
    renderer = FakeRenderer(fail=failure)

    result = _adapter(renderer).render(_request(tmp_path))

    assert result.succeeded is False
    assert result.failure_stage is stage
    assert result.manifest is None
    assert [call[0] for call in renderer.calls] == expected_calls
    assert not hasattr(result, "promote")


@pytest.mark.parametrize(
    "compile_result",
    [None, object(), CommandResult("not-a-bool")],
)
def test_invalid_compile_result_fails_closed(
    tmp_path: Path, compile_result: object
) -> None:
    renderer = FakeRenderer()
    renderer.compile = lambda request: compile_result  # type: ignore[method-assign]

    result = _adapter(renderer).render(_request(tmp_path))

    assert result.succeeded is False
    assert result.failure_stage is RenderFailureStage.COMPILE
    assert result.manifest is None
    assert not any(call[0] in {"render", "concat"} for call in renderer.calls)


@pytest.mark.parametrize(
    "result_factory",
    [
        lambda: None,
        lambda: object(),
        lambda: ArtifactResult(True, None),
        lambda: ArtifactResult("not-a-bool", _artifact("rendered:Proof")),
    ],
)
def test_invalid_scene_render_result_fails_closed(
    tmp_path: Path, result_factory
) -> None:
    renderer = FakeRenderer()
    renderer.render_scene = (  # type: ignore[method-assign]
        lambda request, scene_id: result_factory()
    )

    result = _adapter(renderer).render(_request(tmp_path))

    assert result.succeeded is False
    assert result.failure_stage is RenderFailureStage.SCENE_RENDER
    assert result.manifest is None
    assert not any(call[0] == "concat" for call in renderer.calls)


@pytest.mark.parametrize(
    "result_factory",
    [
        lambda: None,
        lambda: object(),
        lambda: ArtifactResult(True, None),
        lambda: ArtifactResult("not-a-bool", _artifact("final-video")),
    ],
)
def test_invalid_concatenate_result_fails_closed(
    tmp_path: Path, result_factory
) -> None:
    renderer = FakeRenderer()
    renderer.concatenate = (  # type: ignore[method-assign]
        lambda request, slices: result_factory()
    )

    result = _adapter(renderer).render(_request(tmp_path))

    assert result.succeeded is False
    assert result.failure_stage is RenderFailureStage.CONCATENATE
    assert result.manifest is None


def test_changed_scene_is_rendered_even_when_a_certified_slice_exists(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path, certify_proof=True)
    source = request.source_code.replace("helper(2)", "helper(3)")
    request = replace(
        request,
        source_code=source,
        code_hash=sha256_text(source),
        scene_hashes=analyze_source(source, request.ordered_scene_ids).scene_hashes,
    )
    renderer = FakeRenderer()

    result = _adapter(renderer).render(request)

    assert result.succeeded is True
    assert ("render", "Proof") in renderer.calls
    proof = next(item for item in result.manifest.slices if item.scene_id == "Proof")
    assert proof.reused is False


def test_manifest_is_canonical_and_binds_every_render_identity(tmp_path: Path) -> None:
    request = _request(tmp_path)
    first = _adapter(FakeRenderer()).render(request).manifest
    second = _adapter(FakeRenderer()).render(request).manifest

    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.hash == second.hash
    for field, value in (
        ("revision_id", "rev-other"),
        ("render_config_hash", sha256_text("other config")),
        ("renderer_version", "manim-9.9"),
    ):
        changed = replace(request, **{field: value})
        manifest = _adapter(FakeRenderer()).render(changed).manifest
        assert manifest.hash != first.hash
    changed_source = _source().replace("helper(2)", "helper(4)")
    changed = replace(
        request,
        source_code=changed_source,
        code_hash=sha256_text(changed_source),
        scene_hashes=analyze_source(
            changed_source, request.ordered_scene_ids
        ).scene_hashes,
    )
    assert _adapter(FakeRenderer()).render(changed).manifest.hash != first.hash


def test_manifest_identity_does_not_depend_on_storage_uri(tmp_path: Path) -> None:
    request = _request(tmp_path)
    original = _adapter(FakeRenderer()).render(request).manifest
    intro = request.certified_slices["Intro"]
    moved = replace(intro.artifact, uri="memory://different-storage-path")
    changed = replace(
        request, certified_slices={"Intro": replace(intro, artifact=moved)}
    )

    relocated = _adapter(FakeRenderer()).render(changed).manifest

    assert relocated.hash == original.hash
    assert b"memory://" not in relocated.canonical_bytes()


def test_reuse_provenance_is_preserved_and_hash_bound(tmp_path: Path) -> None:
    request = _request(tmp_path)

    manifest = _adapter(FakeRenderer()).render(request).manifest
    intro = manifest.slices[0]

    assert intro.source_revision_id == "rev-1"
    assert intro.source_manifest_hash == sha256_text("manifest-v1")
    assert intro.certification_hash == sha256_text("certificate-v1")
    assert b"source_manifest_hash" in manifest.canonical_bytes()


def test_content_hash_is_stable_across_fresh_and_reused_execution(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    intro = request.certified_slices["Intro"]
    request = replace(
        request,
        certified_slices={
            "Intro": replace(intro, artifact=_artifact("rendered:Intro"))
        },
    )

    reused = _adapter(FakeRenderer()).render(request).manifest
    fresh = (
        _adapter(
            FakeRenderer(), authority=FakeCertificationAuthority(reject_scene="Intro")
        )
        .render(request)
        .manifest
    )

    assert reused.content_hash == fresh.content_hash
    assert reused.evidence_hash != fresh.evidence_hash


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_revision_id", "unrelated-revision"),
        ("source_manifest_hash", sha256_text("untrusted manifest")),
        ("certification_hash", sha256_text("untrusted certificate")),
        ("render_config_hash", sha256_text("old config")),
        ("renderer_version", "manim-old"),
        ("assets_hash", sha256_text("old assets")),
        ("scene_order_hash", sha256_text("old order")),
    ],
)
def test_reuse_requires_certified_lineage_and_matching_environment(
    tmp_path: Path, field: str, value: str
) -> None:
    request = _request(tmp_path)
    stale = replace(request.certified_slices["Intro"], **{field: value})
    request = replace(request, certified_slices={"Intro": stale})
    renderer = FakeRenderer()

    result = _adapter(renderer).render(request)

    assert result.succeeded is True
    assert result.plan.render_scene_ids == ("Intro", "Proof")
    assert ("render", "Intro") in renderer.calls


def test_corrupt_reusable_slice_fails_before_compile(tmp_path: Path) -> None:
    request = _request(tmp_path)
    corrupt_hash = request.certified_slices["Intro"].artifact.hash
    renderer = FakeRenderer()

    result = ManimRenderAdapter(
        renderer,
        MemoryArtifactStore(corrupt_hash=corrupt_hash),
        FakeCertificationAuthority(),
        FakeEnvironmentAuthority(),
    ).render(request)

    assert result.succeeded is False
    assert result.failure_stage is RenderFailureStage.REUSE_VALIDATION
    assert result.manifest is None
    assert renderer.calls == []


def test_authority_rejection_prevents_reuse(tmp_path: Path) -> None:
    renderer = FakeRenderer()
    authority = FakeCertificationAuthority(reject_scene="Intro")

    result = _adapter(renderer, authority=authority).render(_request(tmp_path))

    assert result.succeeded is True
    assert authority.calls == ["Intro"]
    assert result.plan.render_scene_ids == ("Intro", "Proof")
    assert all(not item.reused for item in result.manifest.slices)


def test_source_code_hash_is_revalidated_before_compile(tmp_path: Path) -> None:
    request = _request(tmp_path)

    with pytest.raises(ValueError, match="code_hash"):
        replace(request, source_code="tampered = True\n")


def test_external_file_mutation_cannot_change_immutable_request(tmp_path: Path) -> None:
    external = tmp_path / "candidate.py"
    external.write_text("external = True\n", encoding="utf-8")
    request = _request(tmp_path)
    renderer = FakeRenderer(mutate_path=external)

    result = _adapter(renderer).render(request)

    assert result.succeeded is True
    assert sha256_text(request.source_code) == result.manifest.code_hash
    assert not hasattr(request, "code_path")


def test_explicit_scene_order_drives_concatenation(tmp_path: Path) -> None:
    request = _request(tmp_path)
    order = ("Proof", "Intro")
    intro = replace(
        request.certified_slices["Intro"], scene_order_hash=scene_order_hash(order)
    )
    request = replace(
        request,
        ordered_scene_ids=order,
        certified_slices={"Intro": intro},
    )
    renderer = FakeRenderer()

    result = _adapter(renderer).render(request)

    expected = (
        sha256_text("rendered:Proof"),
        request.certified_slices["Intro"].artifact.hash,
    )
    assert result.succeeded is True
    assert renderer.calls[-1] == ("concat", expected)


def test_duplicate_or_missing_scene_identity_is_rejected(tmp_path: Path) -> None:
    request = _request(tmp_path)

    with pytest.raises(ValueError, match="unique"):
        replace(request, ordered_scene_ids=("Intro", "Intro"))
    with pytest.raises(ValueError, match="exactly match"):
        replace(request, scene_hashes={"Intro": request.scene_hashes["Intro"]})


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
