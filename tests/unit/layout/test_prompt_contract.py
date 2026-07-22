from types import SimpleNamespace

from manim_quality.layout.prompt_contract import extend_layout_prompt, install_prompt_contract


def test_prompt_contract_covers_temporal_states_and_regional_relayout() -> None:
    prompt = extend_layout_prompt("base prompt")

    assert "initial state, transition states, and final state" in prompt
    assert "diagram region, proof region, and title region" in prompt
    assert "choose the safest source-level repair" in prompt


def test_prompt_contract_wraps_only_layout_prompt(tmp_path) -> None:
    module = SimpleNamespace(
        prompt_for=lambda profile, workdir, round_no=1: f"{profile}:{workdir}:{round_no}"
    )

    install_prompt_contract(module)

    assert "initial state" in module.prompt_for("layout", tmp_path, round_no=2)
    assert module.prompt_for("logic", tmp_path) == f"logic:{tmp_path}:1"
