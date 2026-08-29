"""Manim CLI entrypoint with evidence capture installed before scene import."""

from __future__ import annotations

import sys

from manim_quality.operator.runtime_tools.combined_capture import install


def main() -> None:
    install()
    sys.argv[0] = "manim"
    from manim.__main__ import main as manim_main

    manim_main()


if __name__ == "__main__":
    main()
