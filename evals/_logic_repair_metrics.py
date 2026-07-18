"""External scoring and aggregate metrics for frozen logic repair evals."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class RoleUsageMetrics:
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    turns: int
    model_rounds: int
    elapsed_ms: int

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )

    def to_dict(self) -> dict[str, int]:
        return {**asdict(self), "total_tokens": self.total_tokens}

    def plus(self, other: RoleUsageMetrics) -> RoleUsageMetrics:
        values = [
            getattr(self, field) + getattr(other, field)
            for field in self.__dataclass_fields__
        ]
        return RoleUsageMetrics(*values)


@dataclass(frozen=True, slots=True)
class RepairCaseMetrics:
    sample_id: str
    truth: str
    upstream_decision: str
    repair_attempted: bool
    status: str
    attempts: int
    target_restored: bool | None
    over_edit: bool
    coder_usage: RoleUsageMetrics
    verifier_usage: RoleUsageMetrics
    elapsed_ms: int
    error: str | None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["coder_usage"] = self.coder_usage.to_dict()
        data["verifier_usage"] = self.verifier_usage.to_dict()
        return data


def target_lines_restored(
    mutated: str,
    patched: str,
    original: str,
    target_lines: tuple[int, ...],
) -> bool:
    bad_lines = mutated.splitlines()
    expected_lines = original.splitlines()
    patched_lines = {_normalized(line) for line in patched.splitlines()}
    if not target_lines:
        return False
    for line_number in target_lines:
        index = line_number - 1
        if index >= len(bad_lines) or index >= len(expected_lines):
            return False
        bad = _normalized(bad_lines[index])
        expected = _normalized(expected_lines[index])
        if not bad or not expected or bad == expected:
            return False
        if expected not in patched_lines or bad in patched_lines:
            return False
    return True


def summarize_repairs(cases: tuple[RepairCaseMetrics, ...]) -> dict[str, object]:
    known_bad = [case for case in cases if case.truth == "known_bad"]
    known_good = [case for case in cases if case.truth == "known_good"]
    attempted = [case for case in cases if case.repair_attempted]
    ready = [case for case in cases if case.status == "candidate_ready"]
    restored = [case for case in known_bad if case.target_restored is True]
    over_edits = [case for case in known_good if case.over_edit]
    coder = _aggregate(case.coder_usage for case in cases)
    verifier = _aggregate(case.verifier_usage for case in cases)
    return {
        "case_count": len(cases),
        "known_bad": len(known_bad),
        "known_good": len(known_good),
        "repair_attempted": len(attempted),
        "candidate_ready": len(ready),
        "target_restored": len(restored),
        "exact_reference_restoration_rate": _rate(len(restored), len(known_bad)),
        "known_good_over_edit": len(over_edits),
        "known_good_over_edit_rate": _rate(len(over_edits), len(known_good)),
        "errors": sum(case.error is not None for case in cases),
        "coder_usage": coder.to_dict(),
        "verifier_usage": verifier.to_dict(),
        "total_tokens": coder.total_tokens + verifier.total_tokens,
        "elapsed_ms": sum(case.elapsed_ms for case in cases),
        "cases": [case.to_dict() for case in cases],
    }


def _normalized(value: str) -> str:
    return " ".join(value.split())


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _aggregate(values) -> RoleUsageMetrics:
    total = RoleUsageMetrics(0, 0, 0, 0, 0, 0, 0, 0)
    for value in values:
        total = total.plus(value)
    return total
