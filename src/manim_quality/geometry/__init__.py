"""Facts-only geometry inspection contracts and relation evaluation."""

from .schemas import (
    GeometryFact,
    GeometryObject,
    GeometrySnapshot,
    parse_geometry_fact,
    parse_geometry_snapshot,
)

__all__ = [
    "GeometryFact",
    "GeometryObject",
    "GeometrySnapshot",
    "parse_geometry_fact",
    "parse_geometry_snapshot",
]
