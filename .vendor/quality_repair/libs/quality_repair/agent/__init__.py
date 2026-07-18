"""agent — 执行器层：禁改区守卫、进展驱动止损循环、Claude SDK runner。"""

from .controller import LoopResult, run_repair_loop
from .guards import check_edit, make_pre_tool_use_hook
from .runner import ClaudeSDKRunner

__all__ = [
    "ClaudeSDKRunner",
    "LoopResult",
    "check_edit",
    "make_pre_tool_use_hook",
    "run_repair_loop",
]
