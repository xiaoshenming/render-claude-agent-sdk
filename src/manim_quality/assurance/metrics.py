from __future__ import annotations


def summarize(rows: list[dict]) -> dict[str, object]:
    labeled = [row for row in rows if label_value(row) is not None]
    deterministic = _confusion(labeled, lambda row: bool(row["detected_by_tools"]))
    agent_completed = [row for row in rows if isinstance(row.get("agent"), dict)]
    agent_labeled = [
        row for row in agent_completed if label_value(row) is not None
    ]
    agent = _confusion(agent_labeled, agent_positive)
    by_tool: dict[str, int] = {}
    for row in rows:
        for name, report in row.get("deterministic", {}).items():
            by_tool[name] = by_tool.get(name, 0) + (report["status"] == "risk")
    detected = sum(bool(row["detected_by_tools"]) for row in rows)
    return {
        "total": len(rows),
        "deterministic_detected": detected,
        "deterministic_flag_rate": detected / len(rows) if rows else 0,
        "labeled_count": len(labeled),
        "labeled_bad": deterministic["positives"],
        "deterministic_recall": deterministic["recall"],
        "deterministic_precision": deterministic["precision"],
        "deterministic_false_positive_rate": deterministic["false_positive_rate"],
        "agent_completed": len(agent_completed),
        "agent_reviewed": sum(agent_positive(row) for row in agent_completed),
        "agent_recall": agent["recall"],
        "agent_precision": agent["precision"],
        "agent_false_positive_rate": agent["false_positive_rate"],
        "risk_count_by_tool": by_tool,
        "agent_errors": sum("agent_error" in row for row in rows),
    }


def label_value(row: dict) -> bool | None:
    tags = set(row.get("human_tags", ()))
    if "control" in tags:
        return False
    if "human_bad" in tags or tags:
        return True
    verdict = str(row.get("expected_verdict") or "").lower()
    if verdict in {"pass", "通过", "正确"}:
        return False
    return True if verdict else None


def agent_positive(row: dict) -> bool:
    return row.get("agent", {}).get("status") in {"review", "incomplete"}


def _confusion(rows: list[dict], predict) -> dict[str, int | float | None]:
    positive = sum(label_value(row) is True for row in rows)
    negative = sum(label_value(row) is False for row in rows)
    true_positive = sum(label_value(row) is True and predict(row) for row in rows)
    false_positive = sum(
        label_value(row) is False and predict(row) for row in rows
    )
    return {
        "positives": positive,
        "recall": true_positive / positive if positive else None,
        "precision": (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else None
        ),
        "false_positive_rate": false_positive / negative if negative else None,
    }
