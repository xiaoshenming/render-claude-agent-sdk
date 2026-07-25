"""Render-only entrypoint that preserves candidate.py and forces 480p/15fps."""

from candidate import Solution as CandidateSolution
from manim import config

config.pixel_width = 854
config.pixel_height = 480
config.frame_rate = 15


class Solution(CandidateSolution):
    """Unmodified candidate scene exposed from this render module."""

