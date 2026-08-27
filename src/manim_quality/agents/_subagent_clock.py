"""Clock primitive shared by the Reviewer lifecycle protocol."""

import time


def now_ms() -> int:
    return int(time.time() * 1_000)
