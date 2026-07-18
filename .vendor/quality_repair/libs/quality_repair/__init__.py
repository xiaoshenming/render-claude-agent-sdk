"""libs.quality_repair — 成品代码逻辑/重叠修复独立模块。

设计: docs/03-新需求与规划/2026-07-06-逻辑重叠修复独立模块接入设计方案.md
纪律: fail-open（永不阻断主链路）、外部验收（agent 自述无效）、强制回滚。
"""

from .api import RepairBundle, RepairResult, repair
from .interfaces import ToolBox
from .schemas import Budget, CheckResult, budget_for

__all__ = [
    "Budget",
    "CheckResult",
    "RepairBundle",
    "RepairResult",
    "ToolBox",
    "budget_for",
    "repair",
]
