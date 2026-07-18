from types import SimpleNamespace

from evals.workbench_e2e.baseline_stage import render_recovery_prompt
from evals.workbench_e2e.job_runner import run_job
from evals.workbench_e2e.models import WorkloadItem, WorkloadSlot


def test_render_recovery_prompt_is_bounded_and_generic():
    prompt = render_recovery_prompt("ORIGINAL", "x" * 3_000)

    assert prompt.startswith("ORIGINAL")
    assert "重新生成完整代码" in prompt
    assert len(prompt) < 2_200


def test_run_job_converts_unhandled_failure_to_terminal_record(tmp_path):
    class FailingPromptSource:
        def render(self, *args, **kwargs):
            raise RuntimeError("boom")

    item = WorkloadItem("task", "geometry", "hard", 98, "point", "P", "S")
    slot = WorkloadSlot("slot-001", 1, item)
    config = SimpleNamespace(output_root=tmp_path, prompt_source=FailingPromptSource())

    result = run_job(slot, config)

    assert result["status"] == "unhandled_job_error"
    assert (tmp_path / "round-1" / "slot-001" / "job_summary.json").is_file()
    assert not list(tmp_path.rglob("*.tmp"))
