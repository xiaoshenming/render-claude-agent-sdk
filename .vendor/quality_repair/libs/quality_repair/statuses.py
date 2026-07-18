"""quality_repair.statuses — 六态结果常量。

字符串值必须与 apps/render/app/repair_lab/scoring.py 保持完全一致，
但本模块独立可搬运，不 import apps.*，因此在此重复定义。
"""

from __future__ import annotations

from typing import Literal

SUCCESS_CLEAN = "SUCCESS_CLEAN"
SUCCESS_DEGRADED = "SUCCESS_DEGRADED"
REPAIR_FAILED = "REPAIR_FAILED"
REPAIR_WORSE = "REPAIR_WORSE"
REPAIR_UNCHANGED = "REPAIR_UNCHANGED"
REVIEW_ERROR = "REVIEW_ERROR"

RepairStatus = Literal[
    "SUCCESS_CLEAN",
    "SUCCESS_DEGRADED",
    "REPAIR_FAILED",
    "REPAIR_WORSE",
    "REPAIR_UNCHANGED",
    "REVIEW_ERROR",
]

ALL_STATUSES: tuple[str, ...] = (
    SUCCESS_CLEAN,
    SUCCESS_DEGRADED,
    REPAIR_FAILED,
    REPAIR_WORSE,
    REPAIR_UNCHANGED,
    REVIEW_ERROR,
)

# REPAIR_WORSE 是内部态：验收层可以产出它，但 api.repair() 对外必须
# 把它转换为 REPAIR_UNCHANGED 并回退代码（设计方案 D4 红线）。
EXTERNAL_STATUSES: tuple[str, ...] = (
    SUCCESS_CLEAN,
    SUCCESS_DEGRADED,
    REPAIR_FAILED,
    REPAIR_UNCHANGED,
    REVIEW_ERROR,
)
