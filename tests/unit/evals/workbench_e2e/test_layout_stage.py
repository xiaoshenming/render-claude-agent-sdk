from evals.workbench_e2e.layout_probe import normalize_probe, parse_probe_stdout


def test_parse_probe_stdout_uses_last_json_object():
    output = 'warning\n{"ignored": true}\n{"ok": true, "top_overlaps": []}\n'

    assert parse_probe_stdout(output) == {"ok": True, "top_overlaps": []}


def test_normalize_probe_derives_success_from_runner_contract():
    probe = {"error_count": 0, "errors": [], "top_overlaps": [{"kind": "x"}]}

    assert normalize_probe(probe, 0)["ok"] is True
    assert normalize_probe(probe, 1)["ok"] is False


def test_normalize_probe_overrides_stale_success_on_nonzero_exit():
    assert normalize_probe({"ok": True}, 1)["ok"] is False
