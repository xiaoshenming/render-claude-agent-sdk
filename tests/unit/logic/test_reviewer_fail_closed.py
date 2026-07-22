from dataclasses import replace
from pathlib import Path

import pytest
from _reviewer_support import (
    CODE,
    MemorySink,
    PayloadBackend,
    add_citation,
    candidate_citation,
    issue_entry,
    issue_payload,
    limits,
    reviewer,
    service,
    setup_evidence,
)

from manim_quality.agents.profile import coder_profile, reviewer_profile
from manim_quality.agents.runtime import AgentRuntime
from manim_quality.logic._errors import ReviewOutputValidationError
from manim_quality.logic._review_output import bind_review_output
from manim_quality.logic.reviewer import LogicReviewer, LogicReviewError
from manim_quality.revisions.fingerprint import evidence_hash
