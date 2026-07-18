import json
import subprocess
import sys
from pathlib import Path

from tools.quality_repair_checkers.layout_context import build_layout_context


SCRIPT = Path(__file__).resolve().parents[2] / "quality_repair_checkers" / "layout_context.py"


def test_build_layout_context_matches_audit_agent_shape() -> None:
    check_result = {
        "pass": False,
        "status": "layout_failed",
        "summary": "FAIL status=layout_failed blocking=1",
        "blocking_layout_issue_count": 1,
        "blocking_layout_issues": [
            {
                "scene": "Scene_07_Calculate",
                "estimated_duration": 1.0,
                "category": "text_formula_overlap",
                "event": "after_play",
                "step": 1,
                "ratio_of_smaller": 1.0,
                "x_overlap": 0.453612,
                "y_overlap": 0.207412,
                "time_window": {"start": 0.0, "end": 1.0, "recommended_timestamp": 0.5},
                "a": {
                    "path": "mobjects.7",
                    "class": "MathTex",
                    "kind": "formula",
                    "text": "2\\pi r",
                    "parent_path": "mobjects",
                    "bbox": {"left": -0.2268, "right": 0.2268, "top": -0.0821, "bottom": -0.2895},
                },
                "b": {
                    "path": "mobjects.9",
                    "class": "Text",
                    "kind": "text",
                    "text": "长是底面周长",
                    "parent_path": "mobjects",
                    "bbox": {"left": -0.8954, "right": 0.8954, "top": -0.0457, "bottom": -0.3377},
                },
            }
        ],
    }
    probe = {
        "visible_objects": [
            {"path": "mobjects.7", "class": "MathTex", "kind": "formula", "text": "2\\pi r"},
            {"path": "mobjects.9", "class": "Text", "kind": "text", "text": "长是底面周长"},
        ]
    }

    context = build_layout_context(check_result, probe)

    assert list(context) == [
        "active_visible_objects",
        "blocking_layout_issue_count",
        "pass",
        "status",
        "summary",
        "top_blocking_issues",
    ]
    assert context["blocking_layout_issue_count"] == 1
    assert [item["path"] for item in context["active_visible_objects"]] == ["mobjects.7", "mobjects.9"]
    issue = context["top_blocking_issues"][0]
    assert issue["category"] == "text_formula_overlap"
    assert issue["ratio_of_smaller"] == 1.0
    assert issue["x_overlap"] == 0.4536
    assert issue["y_overlap"] == 0.2074
    assert issue["a"]["path"] == "mobjects.7"
    assert issue["a"]["text"] == "2\\pi r"
    serialized = json.dumps(context, ensure_ascii=False)
    assert "parent_path" not in serialized
    assert "Scene_07_Calculate" not in serialized
    assert "estimated_duration" not in serialized


def test_layout_context_cli_converts_existing_check_and_probe_files(tmp_path: Path) -> None:
    check_result = tmp_path / "check_result.json"
    probe_result = tmp_path / "layout_probe.json"
    output = tmp_path / "layout_context.json"
    check_result.write_text(
        json.dumps(
            {
                "ok": True,
                "passed": False,
                "blocking_count": 1,
                "issues": [
                    {
                        "kind": "overlap",
                        "a": "mobjects.1",
                        "b": "mobjects.2",
                        "a_raw": {"path": "mobjects.1", "class": "Text", "text": "A"},
                        "b_raw": {"path": "mobjects.2", "class": "MathTex", "text": "B"},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    probe_result.write_text(
        json.dumps({"visible_objects": [{"path": "mobjects.1"}, {"path": "mobjects.2"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check-result",
            str(check_result),
            "--probe-result",
            str(probe_result),
            "--out",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    stdout_payload = json.loads(result.stdout)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["blocking_layout_issue_count"] == 1
    assert file_payload["top_blocking_issues"][0]["a"]["path"] == "mobjects.1"
