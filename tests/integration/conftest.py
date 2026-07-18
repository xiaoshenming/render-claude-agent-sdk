import sys

import pytest

from manim_quality.layout.adapter import MaterializedQualityRepair

from .overlap_support import VENDOR_ROOT


@pytest.fixture
def vendor_api(monkeypatch: pytest.MonkeyPatch):
    backend = MaterializedQualityRepair(VENDOR_ROOT)
    public = backend.api
    api_module = __import__("libs.quality_repair.api", fromlist=["api"])
    schemas = __import__("libs.quality_repair.schemas", fromlist=["schemas"])
    testing = __import__("libs.quality_repair.testing", fromlist=["testing"])
    public.AgentRunReport = schemas.AgentRunReport
    public.StubChecker = testing.StubChecker
    public.api_module = api_module
    yield backend, public
    for name in ("AgentRunReport", "StubChecker", "api_module"):
        delattr(public, name)
    monkeypatch.delitem(sys.modules, "libs.quality_repair.api", raising=False)
