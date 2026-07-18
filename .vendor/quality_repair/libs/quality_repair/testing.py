"""quality_repair.testing — 内部测试用 stub 实现。"""

from __future__ import annotations

from pathlib import Path

from .schemas import AgentRunReport, Budget, CheckResult


class StubChecker:
    """按预设序列返回 CheckResult；超出序列后重复最后一个。"""

    def __init__(self, results: list[CheckResult]) -> None:
        if not results:
            raise ValueError("StubChecker needs at least one result")
        self._results = list(results)
        self.calls = 0

    def run_check(self, code_path: Path, workdir: Path) -> CheckResult:
        idx = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[idx]


class StubRenderer:
    def __init__(self, ok: bool = True) -> None:
        self._ok = ok

    def render_scene(self, code_path: Path, scene_name: str, out_dir: Path) -> CheckResult:
        if self._ok:
            return CheckResult(ok=True, passed=True, blocking_count=0)
        return CheckResult.failure("stub render failed")

    def frame_at(self, video_path: Path, second: float, out_path: Path) -> Path | None:
        return out_path if self._ok else None


class StubSolver:
    def __init__(self, suggestions: list[dict] | None = None) -> None:
        self._suggestions = suggestions or []

    def solve(self, facts_dir: Path) -> list[dict]:
        return list(self._suggestions)


class FakeRunner:
    """测试专用假执行器：只用于 agent/controller 单测和 monkeypatch。"""

    name = "fake"

    def __init__(
        self,
        *,
        new_code: str | None = None,
        tokens_per_run: int = 1000,
        error: str | None = None,
        final_text: str = "",
    ) -> None:
        self._new_code = new_code
        self._tokens = tokens_per_run
        self._error = error
        self._final_text = final_text
        self.runs = 0

    def run(self, workdir: Path, prompt: str, budget: Budget) -> AgentRunReport:
        self.runs += 1
        if self._error:
            return AgentRunReport(changed=False, tokens_used=0, final_text=self._final_text, error=self._error)
        changed = False
        if self._new_code is not None:
            (workdir / "candidate.py").write_text(self._new_code, encoding="utf-8")
            changed = True
        return AgentRunReport(changed=changed, tokens_used=self._tokens, final_text=self._final_text)
