"""Verify frozen evaluation evidence and produce a fail-closed launch report."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class HoldoutStatus:
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"

    status: str
    sample_count: int
    metrics: dict[str, object]
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {self.NOT_RUN, self.PASSED, self.FAILED}:
            raise ValueError("unknown holdout status")
        if type(self.sample_count) is not int or self.sample_count < 0:
            raise ValueError("sample_count must be non-negative")
        if self.status == self.NOT_RUN and not (self.reason or "").strip():
            raise ValueError("not_run status requires reason")
        if self.status != self.NOT_RUN and self.sample_count == 0:
            raise ValueError("executed status requires samples")
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @classmethod
    def passed(cls, sample_count: int, metrics: dict[str, object]):
        return cls(cls.PASSED, sample_count, metrics)

    @classmethod
    def failed(cls, sample_count: int, metrics: dict[str, object], reason: str):
        return cls(cls.FAILED, sample_count, metrics, reason)

    @classmethod
    def not_run(cls, reason: str):
        return cls(cls.NOT_RUN, 0, {}, reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "sample_count": self.sample_count,
            "metrics": dict(self.metrics),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class HoldoutEvidence:
    logic_good: HoldoutStatus
    logic_bad: HoldoutStatus
    overlap: HoldoutStatus
    modification: HoldoutStatus
    fake_load: HoldoutStatus
    real_render: HoldoutStatus
    canary: HoldoutStatus

    def suites(self) -> dict[str, HoldoutStatus]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def verify_frozen_manifest(path: Path) -> dict[str, str]:
    root = path.resolve(strict=True).parent
    payload = _object(json.loads(path.read_text(encoding="utf-8")), "manifest")
    if payload.get("suite_hash_contract") != "utf8-lf-v1":
        raise ValueError("holdout manifest requires utf8-lf-v1 hashes")
    if payload.get("frozen") is not True:
        raise ValueError("holdout manifest must be frozen")
    suites = payload.get("suites")
    if not isinstance(suites, list) or not suites:
        raise ValueError("holdout manifest requires suites")
    verified: dict[str, str] = {}
    for raw in suites:
        suite = _object(raw, "suite")
        name = _text(suite.get("name"), "suite name")
        relative = Path(_text(suite.get("path"), "suite path"))
        child = (root / relative).resolve(strict=True)
        if not child.is_relative_to(root):
            raise ValueError("suite path escapes manifest root")
        expected = _digest(suite.get("sha256"))
        actual = _file_hash(child)
        if actual != expected:
            raise ValueError(f"suite hash mismatch: {name}")
        child_payload = _object(
            json.loads(child.read_text(encoding="utf-8")), f"suite {name}"
        )
        if child_payload.get("frozen") is not True:
            raise ValueError(f"suite is not frozen: {name}")
        if name in verified:
            raise ValueError(f"duplicate suite name: {name}")
        verified[name] = actual
    return verified


def build_launch_report(
    version: str,
    evidence: HoldoutEvidence,
    *,
    rollback_version: str,
) -> dict[str, object]:
    _text(version, "version")
    _text(rollback_version, "rollback_version")
    suites = evidence.suites()
    blockers = [
        f"{name}:{status.status}"
        for name, status in suites.items()
        if status.status != HoldoutStatus.PASSED
    ]
    return {
        "schema_version": "manim-quality.launch-report.v1",
        "version": version,
        "launch_decision": "HOLD" if blockers else "GO",
        "automatic_repair_enabled": not blockers,
        "rollback_version": rollback_version,
        "blocking_reasons": blockers,
        "suites": {name: status.to_dict() for name, status in suites.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--rollback-version", required=True)
    args = parser.parse_args()
    verified = verify_frozen_manifest(args.manifest)
    evidence = load_evidence(args.evidence)
    report = build_launch_report(
        args.version, evidence, rollback_version=args.rollback_version
    )
    report["verified_manifest_hashes"] = verified
    _write_json(args.output, report)
    print(
        f"launch decision: {report['launch_decision']} "
        f"blockers={len(report['blocking_reasons'])}"
    )
    return 0


def load_evidence(path: Path) -> HoldoutEvidence:
    payload = _object(json.loads(path.read_text(encoding="utf-8")), "evidence")
    values = {}
    for name in HoldoutEvidence.__dataclass_fields__:
        item = _object(payload.get(name), name)
        values[name] = HoldoutStatus(
            str(item.get("status", "")),
            item.get("sample_count", 0),
            _object(item.get("metrics", {}), f"{name} metrics"),
            item.get("reason"),
        )
    return HoldoutEvidence(**values)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _file_hash(path: Path) -> str:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("frozen suite must be UTF-8 text") from error
    canonical = text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _digest(value: object) -> str:
    text = _text(value, "sha256").lower()
    if not text.startswith("sha256:") or len(text) != 71:
        raise ValueError("invalid SHA-256 digest")
    return text


def _object(value: object, name: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"{name} must be an object")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty")
    return value.strip()


if __name__ == "__main__":
    raise SystemExit(main())
