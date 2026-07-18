import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "convert_audit_cases.py"


def run_convert(audit_root: Path, out_root: Path) -> dict:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--audit",
            str(audit_root),
            "--out",
            str(out_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def write_case_file(path: Path, content: str = "content\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_converts_layout_case(tmp_path: Path) -> None:
    audit_root = tmp_path / "audit"
    out_root = tmp_path / "bundle"
    case_root = audit_root / "overlap" / "rand10_direct" / "cases" / "c001"
    write_case_file(case_root / "candidate.py", "print('layout')\n")
    write_case_file(case_root / "layout_context.json", '{"boxes": []}\n')
    write_case_file(case_root / "case.json", '{"scene_name": "Scene_05_RationalClassification"}\n')

    summary = run_convert(audit_root, out_root)

    bundle_case = out_root / "overlap_rand10_direct" / "c001"
    assert (bundle_case / "candidate.py").read_text(encoding="utf-8") == "print('layout')\n"
    assert (bundle_case / "layout_context.json").read_text(encoding="utf-8") == '{"boxes": []}\n'
    bundle = json.loads((bundle_case / "bundle.json").read_text(encoding="utf-8"))
    assert bundle == {
        "job_id": "c001",
        "profile": "layout",
        "code_path": "candidate.py",
        "layout_context": "layout_context.json",
        "evidence_root": "evidence",
        "scene_name": "Scene_05_RationalClassification",
    }
    assert (bundle_case / "case.json").exists()
    assert summary["converted_count"] == 1
    assert summary["skipped"] == []


def test_converts_logic_case(tmp_path: Path) -> None:
    audit_root = tmp_path / "audit"
    out_root = tmp_path / "bundle"
    case_root = audit_root / "logic" / "auto11_contract" / "cases" / "case-alpha"
    write_case_file(case_root / "candidate.py", "print('logic')\n")
    write_case_file(case_root / "logic_contract_context.json", '{"claims": ["ok"]}\n')
    write_case_file(case_root / "source_region.md", "# source\n")
    write_case_file(case_root / "case_manifest.json", '{"scene_name": "Scene_01_Problem"}\n')

    summary = run_convert(audit_root, out_root)

    bundle_case = out_root / "logic_auto11_contract" / "case-alpha"
    assert (bundle_case / "candidate.py").read_text(encoding="utf-8") == "print('logic')\n"
    assert (bundle_case / "logic_contract.json").read_text(encoding="utf-8") == '{"claims": ["ok"]}\n'
    assert (bundle_case / "source_region.md").read_text(encoding="utf-8") == "# source\n"
    bundle = json.loads((bundle_case / "bundle.json").read_text(encoding="utf-8"))
    assert bundle == {
        "job_id": "case-alpha",
        "profile": "logic",
        "code_path": "candidate.py",
        "logic_contract": "logic_contract.json",
        "source_region": "source_region.md",
        "evidence_root": "evidence",
        "scene_name": "Scene_01_Problem",
    }
    assert (bundle_case / "case_manifest.json").exists()
    assert summary["converted_count"] == 1
    assert summary["skipped"] == []


def test_skips_case_with_missing_required_files(tmp_path: Path) -> None:
    audit_root = tmp_path / "audit"
    out_root = tmp_path / "bundle"
    case_root = audit_root / "overlap" / "rand5_direct" / "cases" / "c002"
    write_case_file(case_root / "candidate.py", "print('missing context')\n")

    summary = run_convert(audit_root, out_root)

    assert not (out_root / "overlap_rand5_direct" / "c002").exists()
    assert summary["converted_count"] == 0
    assert summary["skipped_count"] == 1
    assert summary["skipped"] == [
        {
            "source": str(case_root),
            "output_group": "overlap_rand5_direct",
            "reason": "missing_required_files",
            "missing": ["layout_context.json"],
        }
    ]


def test_missing_input_directories_do_not_error(tmp_path: Path) -> None:
    audit_root = tmp_path / "audit"
    out_root = tmp_path / "bundle"
    audit_root.mkdir()

    summary = run_convert(audit_root, out_root)

    assert summary["converted_count"] == 0
    assert summary["skipped_count"] == 0
    assert summary["skipped"] == []
