from .test_targeted_render_fixtures import (replace, Path, pytest, analyze_source, ArtifactResult, CommandResult, EnvironmentEvidence, RenderFailureStage, RenderRequest, ManimRenderAdapter, CertifiedSlice, scene_order_hash, sha256_bytes, sha256_text, ArtifactRef, FakeRenderer, MemoryArtifactStore, FakeCertificationAuthority, FakeEnvironmentAuthority, _request, _certified_slice, _adapter, _artifact, _source, _source_with_base, _ARTIFACT_LABELS)
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
