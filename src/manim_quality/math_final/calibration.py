from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CalibrationMetrics:
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int

    @property
    def precision(self) -> float:
        total = self.true_positive + self.false_positive
        return self.true_positive / total if total else 0.0

    @property
    def recall(self) -> float:
        total = self.true_positive + self.false_negative
        return self.true_positive / total if total else 0.0

    @property
    def false_positive_rate(self) -> float:
        total = self.false_positive + self.true_negative
        return self.false_positive / total if total else 0.0

    def as_dict(self) -> dict[str, int | float]:
        return {
            "true_positive": self.true_positive,
            "false_positive": self.false_positive,
            "true_negative": self.true_negative,
            "false_negative": self.false_negative,
            "precision": self.precision,
            "recall": self.recall,
            "false_positive_rate": self.false_positive_rate,
        }


def calculate_metrics(
    labels: Mapping[str, bool],
    verdicts: Mapping[str, str],
) -> CalibrationMetrics:
    missing = labels.keys() - verdicts.keys()
    if missing:
        raise ValueError(f"missing verdicts for labels: {sorted(missing)}")
    tp = fp = tn = fn = 0
    for key, actually_wrong in labels.items():
        predicted_wrong = verdicts[key] == "MATH_ERROR"
        if actually_wrong and predicted_wrong:
            tp += 1
        elif actually_wrong:
            fn += 1
        elif predicted_wrong:
            fp += 1
        else:
            tn += 1
    return CalibrationMetrics(tp, fp, tn, fn)
