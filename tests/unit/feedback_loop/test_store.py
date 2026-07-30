import json

import pytest

from manim_quality.feedback_loop.models import Candidate, LoopState
from manim_quality.feedback_loop.store import JsonLoopStore


def test_store_rejects_tampered_state(tmp_path):
    path = tmp_path / "loop.json"
    store = JsonLoopStore(path)
    state = LoopState.initial(Candidate("R0", "s0", "v0", "a.py", "a.mp4"))
    store.save(state)
    payload = json.loads(path.read_text())
    payload["state"]["current_candidate"]["source_sha256"] = "changed"
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="checksum"):
        store.load()
