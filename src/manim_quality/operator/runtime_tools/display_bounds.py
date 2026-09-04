"""Compute display bounds from all vertices without truncating a group's tail."""

from __future__ import annotations


def install_complete_bounds(delegate) -> None:
    original = getattr(delegate, "_display_bbox_of", None)
    if not callable(original):
        return

    def display_bounds(scene, mob, fallback_bbox, *, prefer_bbox_corners=False):
        # Text's fallback box deliberately preserves baseline/extent semantics.
        if prefer_bbox_corners:
            return original(scene, mob, fallback_bbox, prefer_bbox_corners=True)
        getter = getattr(mob, "get_all_points", None)
        if not callable(getter):
            return original(scene, mob, fallback_bbox)
        try:
            points = getter()
        except Exception:
            return original(scene, mob, fallback_bbox)
        if not len(points):
            return original(scene, mob, fallback_bbox)
        displayed = delegate._display_points2(
            scene, mob, points, max_points=len(points))
        return delegate._bbox_from_points2(displayed)

    delegate._display_bbox_of = display_bounds
