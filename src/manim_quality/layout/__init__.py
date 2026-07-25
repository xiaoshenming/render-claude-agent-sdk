"""Overlap repair integration behind the platform acceptance boundary."""

from .adapter import MaterializedQualityRepair, OverlapAdapter, OverlapRepairRequest
from .policy import ResidualRiskPolicy
from .result_mapping import OverlapDisposition, OverlapRepairResult

__all__ = [
    "MaterializedQualityRepair",
    "OverlapAdapter",
    "OverlapDisposition",
    "OverlapRepairRequest",
    "OverlapRepairResult",
    "ResidualRiskPolicy",
]
