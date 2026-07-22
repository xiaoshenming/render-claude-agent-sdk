from types import SimpleNamespace


def test_vendor_layout_allows_semantic_equivalent_strings(vendor_api) -> None:
    _backend, _public = vendor_api
    from libs.quality_repair.contract import workdir_files

    assert workdir_files.PROTECTED_DEFAULT["protect_string_literals"] is False


def test_vendor_runtime_receives_platform_layout_prompt_contract(
    vendor_api, tmp_path
) -> None:
    _backend, public = vendor_api
    (tmp_path / "candidate.py").write_text("class Lesson:\n    pass\n", encoding="utf-8")
    (tmp_path / "layout_context.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "layout_issue_digest.json").write_text("{}\n", encoding="utf-8")

    prompt = public.api_module.prompt_for("layout", tmp_path, round_no=1)

    assert "initial state, transition states, and final state" in prompt
    assert "diagram region, proof region, and title region" in prompt


def test_vendor_layout_budget_runs_up_to_five_must_repair_rounds(
    vendor_api, monkeypatch, tmp_path
) -> None:
    backend, public = vendor_api
    code = tmp_path / "candidate.py"
    context = tmp_path / "layout_context.json"
    code.write_text("value = 1\n", encoding="utf-8")
    context.write_text("{}\n", encoding="utf-8")
    captured = {}
    expected = object()

    def fake_repair(bundle, _toolbox):
        captured["budget"] = bundle.budget
        return expected

    monkeypatch.setattr(public, "repair", fake_repair)
    request = SimpleNamespace(
        job_id="five-round-budget",
        code_path=code,
        layout_context_path=context,
        evidence_root=tmp_path / "evidence",
        remaining_tokens=180_000,
    )

    assert backend.repair(request, object()) is expected
    assert captured["budget"].max_rounds == 5
