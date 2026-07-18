from evals.workbench_e2e.process_env import sanitized_subprocess_env


def test_sanitized_subprocess_env_removes_secrets_but_keeps_runtime_paths():
    source = {
        "PATH": "runtime",
        "MANIM_E2E_API_KEY": "secret",
        "ANTHROPIC_AUTH_TOKEN": "secret",
        "SOME_PASSWORD": "secret",
        "NORMAL_SETTING": "ok",
    }

    result = sanitized_subprocess_env(source)

    assert result == {
        "PATH": "runtime",
        "NORMAL_SETTING": "ok",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
    }


def test_sanitized_subprocess_env_overrides_legacy_python_encoding():
    result = sanitized_subprocess_env(
        {"PYTHONIOENCODING": "gbk", "PYTHONUTF8": "0"}
    )

    assert result["PYTHONIOENCODING"] == "utf-8"
    assert result["PYTHONUTF8"] == "1"
