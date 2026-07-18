"""Build logic_contract_context.json without LLM or manual contracts."""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .proof_contracts import proof_claim_contracts
from .route_templates import route_contracts
from .semantic_geometry import semantic_geometry_contracts
from .source_findings import latex_contracts, lifecycle_findings, unescaped_latex_findings
from .source_report import source_region

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GeneratedLogicContract:
    logic_contract: dict[str, Any]
    source_region: str
    findings: list[dict[str, Any]] = field(default_factory=list)

    def write_to(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "logic_contract_context.json").write_text(
            json.dumps(self.logic_contract, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (out_dir / "source_region.md").write_text(self.source_region, encoding="utf-8")
        (out_dir / "review_findings.json").write_text(
            json.dumps({"schema_version": SCHEMA_VERSION, "findings": self.findings}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def generate_logic_contract(code_path: Path, *, manifest_path: Path | None = None) -> GeneratedLogicContract:
    source = code_path.read_text(encoding="utf-8")
    manifest = _read_manifest(manifest_path)
    contracts: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    notes: list[str] = []

    template_contracts, route_notes = route_contracts(source, manifest)
    contracts.extend(template_contracts)
    notes.extend(route_notes)

    semantic_contracts, semantic_findings = semantic_geometry_contracts(source)
    if semantic_contracts:
        contracts = semantic_contracts + contracts
    findings.extend(semantic_findings)

    proof_contract_items, proof_findings = proof_claim_contracts(source)
    if proof_contract_items:
        contracts.extend(proof_contract_items)
    findings.extend(proof_findings)

    latex_findings = unescaped_latex_findings(source)
    if latex_findings:
        contracts = latex_contracts(latex_findings) + contracts
    findings.extend(latex_findings)
    findings.extend(lifecycle_findings(source))

    logic_contract = {
        "schema_version": SCHEMA_VERSION,
        "scene_name": _scene_name(source),
        "kind": contracts[0]["kind"] if contracts else "none",
        "contracts": contracts,
        "issues": findings,
        "notes": " ".join(notes).strip(),
    }
    return GeneratedLogicContract(
        logic_contract=logic_contract,
        source_region=source_region(source, contracts, findings, notes),
        findings=findings,
    )


def _read_manifest(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _scene_name(source: str) -> str:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "unknown"
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if any(isinstance(item, ast.FunctionDef) and item.name == "construct" for item in node.body):
            return node.name
    return "unknown"
