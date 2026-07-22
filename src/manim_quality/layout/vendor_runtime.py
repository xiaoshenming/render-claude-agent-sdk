"""Verified dynamic loader for the materialized quality_repair runtime."""

from __future__ import annotations

import hashlib
import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from .classification import ImpactClassifyingChecker
from .fallback import execute_full_candidate_fallback
from .followup import execute_core_followup
from .policy import agent_token_cap
from .prompt_contract import install_prompt_contract
from .result_mapping import VendorResult
from .runtime_policy import (
    OVERLAP_MAX_ROUNDS,
    OVERLAP_NO_PROGRESS_STOP,
    OVERLAP_SAME_SIGNATURE_STOP,
)

_MANIFEST_SHA256 = "18083bc719d18c22fd5fee461db4d29f9e7d487531fba20a4e57fad2355d1d93"


class MaterializedQualityRepair:
    """Load only a manifest-verified materialized vendor payload."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve(strict=True)
        _verify_materialized_payload(self._root)
        self.api = _load_api(self._root)
        _allow_semantic_equivalent_layout_strings(self._root)
        api_module = importlib.import_module("libs.quality_repair.api")
        _require_module_inside(api_module, self._root)
        install_prompt_contract(api_module)

    def repair(self, request: Any, checker: object) -> VendorResult:
        budget = self.api.Budget(
            max_rounds=OVERLAP_MAX_ROUNDS,
            token_hard_cap=agent_token_cap(request.remaining_tokens),
            no_progress_stop=OVERLAP_NO_PROGRESS_STOP,
            same_signature_stop=OVERLAP_SAME_SIGNATURE_STOP,
            accept_degraded_max_blocking=0,
            accept_degraded_min_reduction_ratio=0.5,
            accept_risk_only_max_blocking=6,
        )
        bundle = self.api.RepairBundle(
            job_id=request.job_id,
            code_path=request.code_path,
            candidate_mode="core",
            layout_context=request.layout_context_path,
            budget=budget,
            evidence_root=request.evidence_root,
        )
        classified = ImpactClassifyingChecker(checker)
        return self.api.repair(bundle, self.api.ToolBox(checker=classified))

    def repair_full_candidate(
        self,
        request: Any,
        checker: object,
        first: VendorResult,
    ) -> VendorResult:
        classified = ImpactClassifyingChecker(checker)
        return execute_full_candidate_fallback(self.api, request, classified, first)

    def repair_core_followup(
        self,
        request: Any,
        checker: object,
        first: VendorResult,
    ) -> VendorResult:
        classified = ImpactClassifyingChecker(checker)
        return execute_core_followup(self.api, request, classified, first)


def _verify_materialized_payload(root: Path) -> None:
    manifest = root / "PAYLOAD_SHA256SUMS.txt"
    payload = manifest.read_bytes()
    if hashlib.sha256(payload).hexdigest() != _MANIFEST_SHA256:
        raise ValueError("quality_repair payload manifest hash mismatch")
    for line in payload.decode("utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        raw_path = root / relative
        if raw_path.is_symlink():
            raise ValueError(f"quality_repair payload symlink denied: {relative}")
        candidate = raw_path.resolve(strict=True)
        if root not in candidate.parents:
            raise ValueError(f"quality_repair payload path escaped: {relative}")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != expected:
            raise ValueError(f"quality_repair payload hash mismatch: {relative}")


def _load_api(root: Path) -> ModuleType:
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    public = importlib.import_module("libs.quality_repair")
    _require_module_inside(public, root)
    return public


def _allow_semantic_equivalent_layout_strings(root: Path) -> None:
    """关闭 vendored layout 的逐字字符串保护，不改写已验签 payload。"""
    module = importlib.import_module(
        "libs.quality_repair.contract.workdir_files"
    )
    _require_module_inside(module, root)
    protected = getattr(module, "PROTECTED_DEFAULT", None)
    if not isinstance(protected, dict):
        raise TypeError("quality_repair PROTECTED_DEFAULT is unavailable")
    protected["protect_string_literals"] = False


def _require_module_inside(module: ModuleType, root: Path) -> None:
    source = Path(module.__file__ or "").resolve(strict=True)
    if root not in source.parents:
        raise ImportError("quality_repair resolved outside verified materialized root")
