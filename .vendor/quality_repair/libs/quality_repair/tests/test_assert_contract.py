import json
from pathlib import Path

from libs.quality_repair import CheckResult
from libs.quality_repair.contract import assert_contract
from libs.quality_repair.schemas import PROFILE_LOGIC


def _make_check(issues: list[dict]) -> CheckResult:
    return CheckResult(ok=True, passed=False, blocking_count=len(issues), issues=issues)


def test_assert_contract_covered_objects_pass(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    (workdir / "facts").mkdir(parents=True)
    (workdir / "facts" / "layout_context.json").write_text(json.dumps({"objects": [{"id": "text1"}, {"id": "text2"}]}), encoding="utf-8")

    ok, reasons = assert_contract(workdir, _make_check([{"kind": "overlap", "a": "text1", "b": "text2"}]))

    assert ok is True
    assert reasons == []


def test_assert_contract_missing_object_fails(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    (workdir / "facts").mkdir(parents=True)
    (workdir / "facts" / "layout_context.json").write_text(json.dumps({"objects": [{"id": "text1"}]}), encoding="utf-8")

    ok, reasons = assert_contract(workdir, _make_check([{"kind": "overlap", "a": "text1", "b": "text_unknown"}]))

    assert ok is False
    assert reasons == ["missing_object:text_unknown"]


def test_assert_contract_collects_objects_from_layout_issues(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    (workdir / "facts").mkdir(parents=True)
    (workdir / "facts" / "layout_context.json").write_text(
        json.dumps(
            {
                "active_visible_objects": [{"path": "mobjects.1"}],
                "top_blocking_issues": [
                    {
                        "a": {"path": "mobjects.5", "class": "Text", "text": "B"},
                        "b": {"path": "mobjects.26", "class": "Polygon"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    ok, reasons = assert_contract(workdir, _make_check([{"kind": "overlap", "a": "mobjects.5", "b": "mobjects.26"}]))

    assert ok is True
    assert reasons == []


def test_assert_contract_facts_unavailable_fails(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    workdir.mkdir(parents=True)

    ok, reasons = assert_contract(workdir, _make_check([{"kind": "overlap", "a": "text1", "b": "text2"}]))

    assert ok is False
    assert reasons == ["facts_unavailable"]


def test_assert_contract_logic_profile_uses_logic_contract_not_layout_facts(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    (workdir / "facts").mkdir(parents=True)
    (workdir / "facts" / "logic_contract.json").write_text(json.dumps({"kind": "equal_length", "expected_coords": [1.0, 2.0, 0.0]}), encoding="utf-8")
    (workdir / "facts" / "source_region.md").write_text("raw source\n", encoding="utf-8")

    ok, reasons = assert_contract(workdir, _make_check([{"kind": "equal_length_wrong"}]), profile=PROFILE_LOGIC)

    assert ok is True
    assert reasons == []


def test_assert_contract_logic_profile_accepts_source_level_contract(tmp_path: Path) -> None:
    workdir = tmp_path / "workdir"
    (workdir / "facts").mkdir(parents=True)
    (workdir / "facts" / "logic_contract.json").write_text(json.dumps({"kind": "no_unescaped_latex_command", "line": 12, "text": "\\dfrac"}), encoding="utf-8")
    (workdir / "facts" / "source_region.md").write_text("raw source\n", encoding="utf-8")

    ok, reasons = assert_contract(workdir, _make_check([{"kind": "unescaped_latex_command"}]), profile=PROFILE_LOGIC)

    assert ok is True
    assert reasons == []
