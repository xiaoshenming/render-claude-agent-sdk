"""quality_repair.interfaces — 外部能力注入协议。

模块独立可搬运：不 import apps.*，不知道 RabbitMQ/MySQL/COS。
真实 checker/渲染器/求解器通过这些 Protocol 注入。
LLM 执行路径固定为 ClaudeSDKRunner，不提供公开替代 runner 入口。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from .schemas import CheckResult


@runtime_checkable
class CheckerAdapter(Protocol):
    """唯一裁判：跑真实 layout probe / logic validator。"""

    def run_check(self, code_path: Path, workdir: Path) -> CheckResult: ...


@runtime_checkable
class RendererAdapter(Protocol):
    """单场景快渲与抽帧（-ql，不做全量重渲）。"""

    def render_scene(self, code_path: Path, scene_name: str, out_dir: Path) -> CheckResult: ...

    def frame_at(self, video_path: Path, second: float, out_path: Path) -> Path | None: ...


@runtime_checkable
class LayoutSolver(Protocol):
    """确定性布局求解器：输入 facts，输出 L1 轴向平移建议。"""

    def solve(self, facts_dir: Path) -> list[dict]: ...


class ToolBox:
    """注入到 repair() 的非 LLM 能力集合。checker 必需，其余可选。"""

    def __init__(
        self,
        *,
        checker: CheckerAdapter,
        renderer: RendererAdapter | None = None,
        solver: LayoutSolver | None = None,
    ) -> None:
        self.checker = checker
        self.renderer = renderer
        self.solver = solver
