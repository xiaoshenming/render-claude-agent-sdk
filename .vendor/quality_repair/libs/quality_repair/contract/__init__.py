"""quality_repair.contract — 合同层：workdir 装配与世界模型相等断言（设计 §七）。"""

from .assert_contract import assert_contract
from .build_workdir import build_workdir

__all__ = ["assert_contract", "build_workdir"]
