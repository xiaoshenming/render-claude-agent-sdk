from .test_targeted_render_fixtures import (replace, Path, pytest, analyze_source, ArtifactResult, CommandResult, EnvironmentEvidence, RenderFailureStage, RenderRequest, ManimRenderAdapter, CertifiedSlice, scene_order_hash, sha256_bytes, sha256_text, ArtifactRef, FakeRenderer, MemoryArtifactStore, FakeCertificationAuthority, FakeEnvironmentAuthority, _request, _certified_slice, _adapter, _artifact, _source, _source_with_base, _ARTIFACT_LABELS)
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
