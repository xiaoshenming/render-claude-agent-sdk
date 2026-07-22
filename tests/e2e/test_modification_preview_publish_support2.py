from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.auth import GatewayHmacAuthenticator
from apps.api.main import ApiSettings, create_app
from manim_quality.contracts import (
    PatchScope,
    QualityState,
    Revision,
    RevisionCreator,
    RevisionStage,
)
from manim_quality.modification.errors import ModificationNotFound
from manim_quality.modification.models import (
    ApprovalReceipt,
    DraftState,
    ModificationContext,
    ModificationDraft,
)
from manim_quality.modification.planner import (
    ModificationScopeError,
    plan_modification,
    validate_modification,
)
from manim_quality.modification.repository import (
    SQLiteModificationRepository,
)
from manim_quality.modification.service import ModificationService
from manim_quality.orchestrator.models import ExecutionRequest, StageAction
from manim_quality.rendering.impact import analyze_source
from manim_quality.rendering.interfaces import RenderEvidence, RenderRequest
from manim_quality.rendering.manifest import ManifestSlice, RenderManifest
from manim_quality.rendering.slices import RenderPlan
from manim_quality.revisions.fingerprint import (
    code_hash,
    scene_fingerprints,
    semantic_fingerprint,
    sha256_bytes,
    sha256_text,
)
from manim_quality.storage import ArtifactRef
from manim_quality.storage._sqlite import open_sqlite
from manim_quality.storage.database import SQLiteRevisionRepository
from manim_quality.storage.intake import IntakeLimits, SQLiteIntakeRepository
from .test_quality_happy_path import VERSIONS
from .test_quality_happy_path import (
    baseline as happy_baseline,
)
from .test_quality_happy_path import (
    execution_request as happy_request,
)
from .test_quality_happy_path import (
    service as quality_service,
)

SOURCE = """\
from manim import *

SCALE = 1

class Intro(Scene):
    def construct(self):
        self.play(Write(Text("Intro")))

class Proof(Scene):
    def construct(self):
        self.play(Write(Text("old")))

class Summary(Scene):
    def construct(self):
        self.play(Write(Text("Summary")))
"""



def _context() -> ModificationContext:
    impact = analyze_source(SOURCE, ("Intro", "Proof", "Summary"))
    preview = RenderRequest(
        "baseline-1",
        SOURCE,
        code_hash(SOURCE),
        impact.scene_hashes,
        ("Intro", "Proof", "Summary"),
        {},
        sha256_text("render-config"),
        "renderer-v1",
        sha256_text("assets"),
    )
    quality = ExecutionRequest(
        "job-1",
        "old-run",
        sha256_text("old-request"),
        sha256_text("question"),
        sha256_text("plan"),
        SOURCE,
        "artifact://candidate.py",
        "artifact://render.json",
        sha256_text("render-config"),
        sha256_text("assets"),
        sha256_text("external"),
        ("Intro", "Proof", "Summary"),
        sha256_text("environment"),
        VERSIONS,
    )
    return ModificationContext(
        "tenant-a", "job-1", "baseline-1", SOURCE, preview, quality
    )


def _artifact(label: str) -> ArtifactRef:
    content = label.encode()
    return ArtifactRef(
        f"artifact://{label}", sha256_bytes(content), len(content), "video/mp4"
    )
